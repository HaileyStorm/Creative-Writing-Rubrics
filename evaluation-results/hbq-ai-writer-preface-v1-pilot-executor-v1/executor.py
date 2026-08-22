#!/usr/bin/env python3
"""Cap-one, provenance-bound executor for Experiment A's frozen pilot cells.

The frozen protocol deliberately has no provider path.  This successor keeps
raw writing and responses in a caller-selected private root, while its public
work root contains only immutable commitments and safe disclosure projections.
"""
from __future__ import annotations

import argparse
import csv
from io import StringIO
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
BASE = HERE.parent / "hbq-ai-writer-preface-v1"
CONTRACT_PATH = HERE / "study-contract.json"
SCHEMA_PATH = REPOSITORY / "schema" / "hbq_judge_response.schema.json"
BINARY_PROMPT_PATH = REPOSITORY / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md"
PUBLIC_BINDING = "executor-binding.json"
PUBLIC_SCHEDULE = "pilot-schedule.jsonl"
PUBLIC_JOURNAL = "execution-journal.jsonl"
PUBLIC_DISCLOSURES = "outbound-disclosures.jsonl"
PUBLIC_SETTLEMENT = "offline-settlement.json"
PRIVATE_MANIFEST = "pilot-inputs.json"
PRIVATE_AUTHORITY = "hanna-provenance-authority.json"
PRIVATE_HANNA_PROJECTION = "hanna-projection.json"
PRIVATE_HANNA_PROJECTION_RECEIPT = "hanna-projection-receipt.json"
PRIVATE_PARENT_HANNA_DATASET = "hanna-parent-dataset.csv"
PRIVATE_CELLS = "cells"
PRIVATE_CAPACITY = "capacity"
CLAIM = "active-epoch-claim.json"
ORPHAN_CLAIM = "active-orphan-adjudication-claim.json"
MODEL = "gpt-5.6-sol"
REASONING = "high"
PROVIDER = "codex"
CAPACITY_MAX_AGE = timedelta(minutes=10)
ARMS = ("none", "current_full", "strictness_only")
ORIGINS = ("ai_written", "non_ai_written")
HEX = frozenset("0123456789abcdef")
OPAQUE_ID = re.compile(r"^[a-f0-9]{16}$")
LEAK_TOKENS = ("ai_written", "non_ai_written", "deepseek", "gpt", "grok", "ox-alpha", "model")
CONTEXT_PROVENANCE_HEADER = re.compile(r"(?im)^\s*(actual[_ -]?origin|source[_ -]?model|declared[_ -]?origin)\s*[:=]")
CURRENT_FULL_BYTES = 2644
CURRENT_FULL_SHA256 = "5498a254cc9e3fe2ce2fcfa11aab318bd0b4996c1c441f0a7d540d9b1bfc7e96"
HANNA_PROJECTION_RECIPE = "hanna-story-prompt-projection-v1: sort by executor_id; bind exact CSV Story and Prompt plus verified provenance"
HANNA_EXTRACTION_RECIPE = "hanna-story-prompt-extraction-v1: preserve parent CSV row order and emit hanna_item_id,Story,Prompt with LF records"
PINNED_HANNA_PARENT_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
HANNA_PARENT_FIELDS = ("Story ID", "Prompt", "Human", "Story", "Model", "Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity", "Worker ID", "Assignment ID", "Work time in seconds", "Name")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON object: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"Immutable artifact drifted: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        Path(temporary).replace(path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _append(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError("Partial journal write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"Partial committed journal tail: {path}")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line:
            raise ValueError(f"Blank committed journal row: {path}")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Malformed committed journal row: {path}") from error
        if not isinstance(value, dict):
            raise ValueError(f"Non-object committed journal row: {path}")
        rows.append(value)
    return rows


def _fingerprint(path: Path, *, reveal_path: bool = False) -> dict[str, Any]:
    actual = path.resolve()
    if not actual.is_file():
        raise ValueError(f"Missing bound file: {actual}")
    data = actual.read_bytes()
    result: dict[str, Any] = {"bytes": len(data), "sha256": _sha256(data)}
    if reveal_path:
        result["path"] = str(actual)
    else:
        result["path_sha256"] = _sha256(str(actual))
    return result


def _tree_fingerprint(path: Path) -> dict[str, Any]:
    root = path.resolve()
    if not root.is_dir():
        raise ValueError(f"Missing bound directory: {root}")
    rows = []
    for item in sorted(root.rglob("*")):
        if item.is_file():
            data = item.read_bytes()
            rows.append({"path": item.relative_to(root).as_posix(), "bytes": len(data), "sha256": _sha256(data)})
    if not rows:
        raise ValueError(f"Bound directory is empty: {root}")
    return {"files": len(rows), "sha256": _sha256(_canonical(rows))}


def _codex_cli_attestation() -> dict[str, Any]:
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is unavailable for local runtime attestation")
    completed = subprocess.run([executable, "--version"], text=True, encoding="utf-8", capture_output=True, timeout=30.0, check=False)
    if completed.returncode or not completed.stdout.strip():
        raise ValueError("Codex CLI version attestation failed")
    status = subprocess.run([executable, "login", "status"], text=True, encoding="utf-8", capture_output=True, timeout=30.0, check=False)
    status_text = (status.stdout + "\n" + status.stderr).strip()
    if status.returncode or "Logged in using ChatGPT" not in status_text or "API key" in status_text:
        raise ValueError("Codex CLI must attest ChatGPT login; API-key or unknown routing is forbidden")
    return {"executable": _fingerprint(Path(executable)), "version": completed.stdout.strip(), "auth_channel": "ChatGPT", "api_key_routing": False}


def _disjoint(left: Path, right: Path) -> bool:
    first, second = left.resolve(), right.resolve()
    return first != second and first not in second.parents and second not in first.parents


def _load_base() -> Any:
    specification = importlib.util.spec_from_file_location("hbq_ai_writer_preface_v1_base", BASE / "study.py")
    if specification is None or specification.loader is None:
        raise RuntimeError("Cannot load frozen AI-writer/preface protocol")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _runner() -> Any:
    from hbqrs import runner
    return runner


def contract() -> dict[str, Any]:
    value = _json_object(CONTRACT_PATH)
    expected = {
        "format_version": 1,
        "study_id": "hbq-ai-writer-preface-v1-pilot-executor-v1",
        "purpose": "A separately reviewed, judge-side executor for the frozen Experiment A pilot; it does not amend the sealed v1 protocol or implement writer-side Experiment B.",
        "base_protocol": {
            "study_id": "hbq-ai-writer-preface-v1",
            "study_contract_sha256": "ce4f585056a9ba32db9320bf4c199f3f8f6369d264889f116fabb7916f8bede2",
            "study_runtime_sha256": "cb91c7073f20eea1c398afd003c04f3d288a1681c46f01ca592589a6c2fe7d31",
        },
        "hanna_parent": {"sha256": PINNED_HANNA_PARENT_SHA256, "fields": list(HANNA_PARENT_FIELDS), "extraction_recipe": HANNA_EXTRACTION_RECIPE},
        "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING, "primary": True, "paid_api": False, "human_judgment": False, "fallbacks": "forbidden"},
        "pilot": {"inputs": 4, "actual_origin_allocation": {"ai_written": 2, "non_ai_written": 2}, "arms": list(ARMS), "fresh_sessions_per_arm": 2, "cells": 24, "question_geometry": "one full compiled HBQ question sequence per cell", "provider_calls_per_cell": 1},
        "execution": {"unscored_capacity_preflight": "required_before_each_scored_cell_and_never counts as a scored cell", "scored_cells_per_epoch": 1, "scored_attempts_per_cell": 1, "resend_after_any_terminal_or_uncertain_attempt": False, "outcome_dependent_retry_or_stopping": False, "remote_gate": "--allow-remote", "offline_settlement_only": True},
        "evidence": {"public_root": "commitments, schedule, disclosures, and settlement status only", "private_root": "exact frozen source/context inputs, rendered prompts, raw responses, and provider records", "roots_must_be_disjoint": True, "actual_provenance_never_sent": True},
        "out_of_scope": ["writer-side Experiment B", "Experiment C", "prompt or rubric modification", "human or paid evaluation", "non-GPT fallback", "automatic production change"],
    }
    if value != expected:
        raise ValueError("Pilot executor contract drifted")
    base = _load_base()
    base.load_contract()
    if _sha256((BASE / "study-contract.json").read_bytes()) != expected["base_protocol"]["study_contract_sha256"]:
        raise ValueError("Frozen base contract bytes drifted")
    if _sha256((BASE / "study.py").read_bytes()) != expected["base_protocol"]["study_runtime_sha256"]:
        raise ValueError("Frozen base runtime bytes drifted")
    return value


def _within(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _input_binding(value: object, *, private_root: Path, role: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"}:
        raise ValueError(f"{role} binding is malformed")
    path, size, digest = value.get("path"), value.get("bytes"), value.get("sha256")
    if not isinstance(path, str) or type(size) is not int or size < 0 or not _is_sha256(digest):
        raise ValueError(f"{role} binding has invalid fields")
    actual = Path(path).resolve()
    if not _within(private_root, actual):
        raise ValueError(f"{role} must remain inside the private root")
    found = _fingerprint(actual, reveal_path=True)
    if found != {"path": str(actual), "bytes": size, "sha256": digest}:
        raise ValueError(f"{role} bytes drifted")
    return {"path": str(actual), "bytes": size, "sha256": digest}


def _has_leak(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in LEAK_TOKENS)


def _hanna_story_prompt_projection(parent_path: Path) -> bytes:
    try:
        with parent_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != list(HANNA_PARENT_FIELDS):
                raise ValueError("Parent HANNA dataset schema drifted")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("Parent HANNA dataset is unreadable") from error
    groups: dict[str, tuple[str, str, str, int]] = {}
    order: list[str] = []
    for row in rows:
        if set(row) != set(HANNA_PARENT_FIELDS) or any(not isinstance(row.get(key), str) for key in ("Story ID", "Prompt", "Story", "Model")) or not row["Story ID"]:
            raise ValueError("Parent HANNA dataset has malformed rows")
        story_id = row["Story ID"]
        triple = (row["Prompt"], row["Story"], row["Model"])
        prior = groups.get(story_id)
        if prior is None:
            groups[story_id] = (*triple, 1)
            order.append(story_id)
        elif prior[:3] != triple:
            raise ValueError("Parent HANNA duplicate Story ID disagrees on Prompt, Story, or Model")
        else:
            groups[story_id] = (*prior[:3], prior[3] + 1)
    if any(value[3] != 3 for value in groups.values()):
        raise ValueError("Parent HANNA Story ID must have exactly three consistent annotation rows")
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["hanna_item_id", "Story", "Prompt"], lineterminator="\n")
    writer.writeheader()
    writer.writerows({"hanna_item_id": story_id, "Story": groups[story_id][1], "Prompt": groups[story_id][0]} for story_id in order)
    return output.getvalue().encode("utf-8")


def _authority(private_root: Path) -> dict[str, Any]:
    path = private_root / PRIVATE_AUTHORITY
    value = _json_object(path)
    if set(value) != {"format_version", "base_study_id", "parent_hanna_dataset", "hanna_source", "provenance_source", "projection_receipt", "items"} or value.get("format_version") != 1 or value.get("base_study_id") != "hbq-ai-writer-preface-v1" or not isinstance(value.get("items"), list):
        raise ValueError("Bound HANNA/provenance authority identity drifted")
    parent_binding = _input_binding(value.get("parent_hanna_dataset"), private_root=private_root, role="parent HANNA dataset")
    hanna_binding = _input_binding(value.get("hanna_source"), private_root=private_root, role="HANNA source authority")
    provenance_binding = _input_binding(value.get("provenance_source"), private_root=private_root, role="provenance source authority")
    receipt_binding = _input_binding(value.get("projection_receipt"), private_root=private_root, role="HANNA projection receipt")
    if Path(str(receipt_binding["path"])).resolve() != (private_root / PRIVATE_HANNA_PROJECTION_RECEIPT).resolve():
        raise ValueError("HANNA projection receipt must use the fixed private path")
    if Path(str(parent_binding["path"])).resolve() != (private_root / PRIVATE_PARENT_HANNA_DATASET).resolve():
        raise ValueError("Parent HANNA dataset must use the fixed private path")
    if parent_binding["sha256"] != PINNED_HANNA_PARENT_SHA256:
        raise ValueError("Parent HANNA dataset does not match the pinned exact source hash")
    if Path(str(hanna_binding["path"])).read_bytes() != _hanna_story_prompt_projection(Path(str(parent_binding["path"]))):
        raise ValueError("HANNA Story/Prompt source is not the deterministic parent-dataset extraction")
    try:
        hanna_rows = list(csv.DictReader(Path(str(value["hanna_source"]["path"])).open(encoding="utf-8-sig", newline="")))
        provenance_payload = _json_object(Path(str(value["provenance_source"]["path"])))
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("Bound HANNA/provenance authority source is unreadable") from error
    records_value = provenance_payload.get("records") if provenance_payload.get("format_version") == 1 else None
    if set(provenance_payload) != {"format_version", "records"} or not isinstance(records_value, list):
        raise ValueError("Bound provenance source must be a structured record-level authority")
    provenance_records = {str(row.get("hanna_item_id")): row for row in records_value if isinstance(row, Mapping) and set(row) == {"hanna_item_id", "actual_origin", "source_model", "matching_stratum"}}
    if len(provenance_records) != len(records_value):
        raise ValueError("Bound provenance source has duplicate or malformed records")
    records: dict[str, dict[str, str]] = {}
    projection_items: list[dict[str, str]] = []
    for item in value["items"]:
        if not isinstance(item, Mapping) or set(item) != {"executor_id", "hanna_item_id", "actual_origin", "source_model", "matching_stratum"}:
            raise ValueError("HANNA/provenance authority item drifted")
        executor_id, hanna_item_id, actual_origin, source_model, matching_stratum = item.get("executor_id"), item.get("hanna_item_id"), item.get("actual_origin"), item.get("source_model"), item.get("matching_stratum")
        if not isinstance(executor_id, str) or not OPAQUE_ID.fullmatch(executor_id) or _has_leak(executor_id) or not isinstance(hanna_item_id, str) or not hanna_item_id or _has_leak(hanna_item_id) or actual_origin not in ORIGINS or not isinstance(source_model, str) or not source_model or not isinstance(matching_stratum, str) or not matching_stratum or executor_id in records:
            raise ValueError("HANNA/provenance authority leaks a treatment label or is malformed")
        selected = [row for row in hanna_rows if row.get("hanna_item_id") == hanna_item_id]
        if len(selected) != 1 or set(selected[0]) != {"hanna_item_id", "Story", "Prompt"}:
            raise ValueError("HANNA authority must select one exact Story/Prompt CSV row")
        if provenance_records.get(hanna_item_id) != {"hanna_item_id": hanna_item_id, "actual_origin": actual_origin, "source_model": source_model, "matching_stratum": matching_stratum}:
            raise ValueError("HANNA/provenance authority item does not match its structured provenance record")
        records[executor_id] = {"hanna_item_id": hanna_item_id, "actual_origin": actual_origin, "source_model": source_model, "matching_stratum": matching_stratum, "story": selected[0]["Story"], "prompt": selected[0]["Prompt"]}
        projection_items.append({"executor_id": executor_id, "hanna_item_id": hanna_item_id, "story": selected[0]["Story"], "prompt": selected[0]["Prompt"], "actual_origin": actual_origin, "source_model": source_model, "matching_stratum": matching_stratum})
    projection = {"format_version": 1, "recipe": HANNA_PROJECTION_RECIPE, "parent_dataset_sha256": parent_binding["sha256"], "extraction_output_sha256": hanna_binding["sha256"], "pinned_provenance_sha256": provenance_binding["sha256"], "items": sorted(projection_items, key=lambda item: item["executor_id"])}
    receipt = _json_object(Path(str(receipt_binding["path"])))
    if set(receipt) != {"format_version", "extraction_recipe", "parent_dataset_sha256", "extraction_output_sha256", "recipe", "pinned_provenance_sha256", "projection", "projection_output_sha256"} or receipt.get("format_version") != 1 or receipt.get("extraction_recipe") != HANNA_EXTRACTION_RECIPE or receipt.get("parent_dataset_sha256") != parent_binding["sha256"] or receipt.get("extraction_output_sha256") != hanna_binding["sha256"] or receipt.get("recipe") != HANNA_PROJECTION_RECIPE or receipt.get("pinned_provenance_sha256") != provenance_binding["sha256"]:
        raise ValueError("HANNA projection receipt does not bind pinned sources and recipe")
    projection_binding = _input_binding(receipt.get("projection"), private_root=private_root, role="HANNA projection output")
    if receipt.get("projection_output_sha256") != projection_binding["sha256"] or Path(str(projection_binding["path"])).resolve() != (private_root / PRIVATE_HANNA_PROJECTION).resolve():
        raise ValueError("HANNA projection output must use the fixed private path")
    if _json_object(Path(str(projection_binding["path"]))) != projection:
        raise ValueError("HANNA projection output is not the deterministic receipt-bound derivation")
    return {"binding": _fingerprint(path), "records": records, "sources": {"parent_hanna_dataset": parent_binding, "hanna_source": hanna_binding, "provenance_source": provenance_binding}, "projection": {"receipt": receipt_binding, "output": projection_binding}}


def _private_manifest(private_root: Path) -> dict[str, Any]:
    root = private_root.resolve()
    manifest_path = root / PRIVATE_MANIFEST
    if not root.is_dir() or not manifest_path.is_file():
        raise ValueError("Private pilot root must contain pilot-inputs.json")
    value = _json_object(manifest_path)
    if set(value) != {"format_version", "base_study_id", "phase", "items"} or value.get("format_version") != 1 or value.get("base_study_id") != "hbq-ai-writer-preface-v1" or value.get("phase") != "pilot" or not isinstance(value.get("items"), list):
        raise ValueError("Private pilot manifest identity drifted")
    authority = _authority(root)
    items = value["items"]
    if len(items) != 4:
        raise ValueError("Pilot manifest must name exactly four frozen inputs")
    ids: set[str] = set()
    origins: list[str] = []
    normalized: list[dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, Mapping) or set(entry) != {"executor_id", "artifact", "contexts", "task_contract"}:
            raise ValueError("Pilot item schema drifted")
        item_id = entry.get("executor_id")
        authority_item = authority["records"].get(item_id) if isinstance(item_id, str) else None
        if not isinstance(item_id, str) or not OPAQUE_ID.fullmatch(item_id) or _has_leak(item_id) or item_id in ids or authority_item is None:
            raise ValueError("Pilot item identity or verified provenance drifted")
        actual_origin, source_model, matching_stratum = authority_item["actual_origin"], authority_item["source_model"], authority_item["matching_stratum"]
        ids.add(item_id); origins.append(actual_origin)
        contexts = entry.get("contexts")
        if not isinstance(contexts, list) or len(contexts) != 1:
            raise ValueError("Pilot item must bind exactly one HANNA Prompt context")
        bound_contexts = [_input_binding(item, private_root=root, role="context") for item in contexts]
        if any(CONTEXT_PROVENANCE_HEADER.search(Path(str(item["path"])).read_text(encoding="utf-8-sig")) for item in bound_contexts):
            raise ValueError("Pilot context leaks actual-origin or source-model metadata")
        artifact = _input_binding(entry.get("artifact"), private_root=root, role="artifact")
        artifact_text = Path(str(artifact["path"])).read_text(encoding="utf-8-sig")
        context_text = Path(str(bound_contexts[0]["path"])).read_text(encoding="utf-8-sig")
        if artifact_text != authority_item["story"] or context_text != authority_item["prompt"]:
            raise ValueError("Pilot artifact/context must exactly bind the selected HANNA Story/Prompt row")
        normalized.append({"item_id": item_id, "actual_origin": actual_origin, "source_model": source_model, "matching_stratum": matching_stratum, "artifact": artifact, "contexts": bound_contexts, "task_contract": _input_binding(entry.get("task_contract"), private_root=root, role="task contract")})
    if {origin: origins.count(origin) for origin in ORIGINS} != {"ai_written": 2, "non_ai_written": 2}:
        raise ValueError("Pilot actual-origin allocation drifted")
    matching_strata: dict[str, list[str]] = {}
    for item in normalized:
        matching_strata.setdefault(str(item["matching_stratum"]), []).append(str(item["actual_origin"]))
    if len(matching_strata) != 2 or any(sorted(levels) != list(ORIGINS) for levels in matching_strata.values()):
        raise ValueError("Pilot matching strata must each contain one item from each actual-origin level")
    return {"manifest": _fingerprint(manifest_path), "authority": authority, "items": normalized}


def _compiled_questions(item: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
    from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
    from hbqrs.paths import bundles_path, registry_path

    task_contract = _json_object(Path(str(item["task_contract"]["path"])))
    if task_contract.get("artifact_id") != item["item_id"]:
        raise ValueError("Pilot task contract artifact_id drifted")
    bundle = resolve_bundle(load_bundles(bundles_path()), "prose.short_story")
    compiled = compile_bundle(load_modules(registry_path()), bundle, task_contract=task_contract)
    role_order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda value: role_order.get(str(value.get("role")), 99))
    ids = [str(question["question"]["id"]) for question in questions]
    if not questions or len(set(ids)) != len(ids):
        raise ValueError("Compiled HBQ question sequence is empty or duplicates IDs")
    runner = _runner()
    return questions, _sha256(_canonical(runner._question_payload(questions)))


def _prefix(arm: str) -> str:
    base = _load_base()
    frozen = base.load_contract()
    if arm == "none":
        return ""
    if arm == "current_full":
        raw = base.CURRENT_PREFIX.read_bytes()
        if _sha256(raw) != frozen["bound_assets"]["current_judge_prefix"]["sha256"]:
            raise ValueError("Current judge prefix drifted")
        return base.CURRENT_PREFIX.read_text(encoding="utf-8")
    if arm == "strictness_only":
        text = str(frozen["bound_assets"]["strictness_only"]["text"])
        if _sha256(text) != frozen["bound_assets"]["strictness_only"]["sha256"]:
            raise ValueError("Strictness-only preface drifted")
        return text
    raise ValueError("Unknown Experiment A arm")


def _binary_prompt_for_arm(arm: str) -> str:
    prefix = _prefix(arm)
    binary = BINARY_PROMPT_PATH.read_text(encoding="utf-8")
    if arm == "none":
        return binary.strip()
    rendered = prefix.strip() + "\n\n" + binary.strip()
    if arm == "current_full" and (len(rendered.encode("utf-8")) != CURRENT_FULL_BYTES or _sha256(rendered) != CURRENT_FULL_SHA256):
        raise ValueError("Current-full production composition drifted")
    return rendered


def _rendered_prompt(item: Mapping[str, Any], arm: str) -> tuple[str, list[str], str]:
    if arm not in ARMS:
        raise ValueError("Unknown Experiment A arm")
    questions, question_sha256 = _compiled_questions(item)
    runner = _runner()
    artifact = runner._read_text_record(Path(str(item["artifact"]["path"])))
    contexts = [runner._read_text_record(Path(str(value["path"]))) for value in item["contexts"]]
    prompt = runner._render_prompt(
        binary_prompt=_binary_prompt_for_arm(arm),
        artifact=artifact,
        contexts=contexts,
        bundle_id="prose.short_story",
        artifact_id=str(item["item_id"]),
        questions=questions,
        provider=PROVIDER,
        model=MODEL,
    )
    return prompt, [str(question["question"]["id"]) for question in questions], question_sha256


def _schedule(private: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in private["items"]:
        for arm in ARMS:
            for fresh_session in (1, 2):
                prompt, question_ids, question_sha256 = _rendered_prompt(item, arm)
                result.append({
                    "sequence": len(result) + 1,
                    "item_id": item["item_id"],
                    "arm": arm,
                    "fresh_session": fresh_session,
                    "prompt_sha256": _sha256(prompt),
                    "prompt_bytes": len(prompt.encode("utf-8")),
                    "question_ids_sha256": _sha256(_canonical(question_ids)),
                    "question_count": len(question_ids),
                    "compiled_question_payload_sha256": question_sha256,
                })
    if len(result) != 24 or len({row["sequence"] for row in result}) != 24:
        raise ValueError("Pilot schedule geometry drifted")
    return result


def _safe_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item["item_id"],
        "artifact": _fingerprint(Path(str(item["artifact"]["path"]))),
        "contexts": [_fingerprint(Path(str(value["path"]))) for value in item["contexts"]],
        "task_contract": _fingerprint(Path(str(item["task_contract"]["path"]))),
    }


def _expected_binding(private_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixed = contract()
    private = _private_manifest(private_root)
    schedule = _schedule(private)
    binding = {
        "format_version": 1,
        "study_id": fixed["study_id"],
        "contract": _fingerprint(CONTRACT_PATH),
        "base_protocol": {"study_contract": _fingerprint(BASE / "study-contract.json"), "study_runtime": _fingerprint(BASE / "study.py")},
        "runtime": {
            "executor": _fingerprint(HERE / "executor.py"),
            "binary_prompt": _fingerprint(BINARY_PROMPT_PATH),
            "response_schema": _fingerprint(SCHEMA_PATH),
            "current_judge_prefix": _fingerprint(REPOSITORY / "prompts" / "judge" / "JUDGE_PREFIX.md"),
            "runner": _fingerprint(REPOSITORY / "src" / "hbqrs" / "runner.py"),
            "core": _fingerprint(REPOSITORY / "src" / "hbqrs" / "core.py"),
            "registry": _tree_fingerprint(REPOSITORY / "registry"),
            "bundles": _tree_fingerprint(REPOSITORY / "bundles"),
            "codex_cli": _codex_cli_attestation(),
            "normalization": "hbqrs.runner._parse_model_json plus _normalize_batch bound by runner.py fingerprint",
            "current_full": {"bytes": CURRENT_FULL_BYTES, "sha256": CURRENT_FULL_SHA256},
        },
        "provider": fixed["provider"],
        "private_manifest": private["manifest"],
        "hanna_provenance_authority": {
            "authority": private["authority"]["binding"],
            "sources": {key: _fingerprint(Path(str(value["path"]))) for key, value in private["authority"]["sources"].items()},
            "projection": {key: _fingerprint(Path(str(value["path"]))) for key, value in private["authority"]["projection"].items()},
        },
        "inputs": [_safe_item(item) for item in private["items"]],
        "schedule_sha256": _sha256(_canonical(schedule)),
        "schedule_count": len(schedule),
        "actual_provenance": "private selection-only; never a remote disclosure field",
    }
    return binding, schedule


def _verify(work: Path, private_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root, private = work.resolve(), private_root.resolve()
    if not _disjoint(root, private):
        raise ValueError("Public and private evidence roots must be disjoint")
    expected, schedule = _expected_binding(private)
    if _json_object(root / PUBLIC_BINDING) != expected or _rows(root / PUBLIC_SCHEDULE) != schedule:
        raise ValueError("Prepared pilot binding or schedule drifted")
    return expected, schedule


def prepare(work: Path, private_root: Path) -> dict[str, Any]:
    root, private = work.resolve(), private_root.resolve()
    if not _disjoint(root, private):
        raise ValueError("Public and private evidence roots must be disjoint")
    if root.exists() and any(root.iterdir()):
        raise ValueError("Prepare requires a fresh, empty public work root")
    binding, schedule = _expected_binding(private)
    root.mkdir(parents=True, exist_ok=True)
    _atomic_json(root / PUBLIC_BINDING, binding)
    for cell in schedule:
        _append(root / PUBLIC_SCHEDULE, cell)
    _verify(root, private)
    return {"provider_calls": 0, "pilot_cells": len(schedule), "scored_cells_remaining": len(schedule)}


def _claim(work: Path, *, journal: Path | None = None) -> Path:
    path = work / CLAIM
    value = {"format_version": 1, "pid": os.getpid(), "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha256((HERE / "executor.py").read_bytes()), "pre_intent_journal_sha256": _sha256(journal.read_bytes()) if journal is not None and journal.exists() else _sha256(b"")}
    descriptor: int
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError("Exclusive epoch claim exists; stop without duplicate dispatch") from error
    try:
        payload = _canonical(value) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            raise OSError("Partial epoch claim write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _claim_value(path: Path) -> dict[str, Any]:
    value = _json_object(path)
    if set(value) != {"format_version", "pid", "claimed_at", "executor_sha256", "pre_intent_journal_sha256"} or value.get("format_version") != 1 or type(value.get("pid")) is not int or value["pid"] < 1 or value.get("executor_sha256") != _sha256((HERE / "executor.py").read_bytes()) or not _is_sha256(value.get("pre_intent_journal_sha256")):
        raise ValueError("Epoch claim is malformed or belongs to different executor bytes")
    return value


def _orphan_claim(work: Path, stale_claim_sha256: str) -> Path:
    path = work / ORPHAN_CLAIM
    value = {
        "format_version": 1,
        "pid": os.getpid(),
        "claimed_at": datetime.now(UTC).isoformat(),
        "executor_sha256": _sha256((HERE / "executor.py").read_bytes()),
        "stale_claim_sha256": stale_claim_sha256,
    }
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError("Exclusive orphan adjudication claim exists; stop without duplicate recovery") from error
    try:
        payload = _canonical(value) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            raise OSError("Partial orphan adjudication claim write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _orphan_claim_value(path: Path) -> dict[str, Any]:
    value = _json_object(path)
    if set(value) != {"format_version", "pid", "claimed_at", "executor_sha256", "stale_claim_sha256"} or value.get("format_version") != 1 or type(value.get("pid")) is not int or value["pid"] < 1 or value.get("executor_sha256") != _sha256((HERE / "executor.py").read_bytes()) or not _is_sha256(value.get("stale_claim_sha256")):
        raise ValueError("Orphan adjudication claim is malformed or belongs to different executor bytes")
    return value


def _cleanup_stale_orphan_claim(work: Path, *, stale_claim_sha256: str | None = None) -> None:
    path = work / ORPHAN_CLAIM
    if not path.exists():
        return
    value = _orphan_claim_value(path)
    if stale_claim_sha256 is not None and value["stale_claim_sha256"] != stale_claim_sha256:
        raise ValueError("Orphan adjudication claim binds a different stale epoch")
    if not _pid_dead(int(value["pid"])):
        raise ValueError("Exclusive orphan adjudication claim exists; stop without duplicate recovery")
    path.unlink()


def _cleanup_completed_epoch_claim(work: Path, private_root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    """Remove only a dead epoch whose journal is already fully settled."""
    path = work / CLAIM
    if not path.exists():
        return
    claim = _claim_value(path)
    if not _pid_dead(int(claim["pid"])):
        return
    records = _rows(work / PUBLIC_JOURNAL)
    if len(records) % 2:
        return
    try:
        _completed(work, schedule, private_root)
    except ValueError:
        return
    path.unlink()


def _next_orphan_authority_path(work: Path, sequence: int) -> tuple[int, Path]:
    root = work / "orphan-authority" / f"{sequence:04d}"
    versions: list[int] = []
    if root.exists():
        if not root.is_dir():
            raise ValueError("Orphan authority root is malformed")
        for candidate in root.glob("v*.json"):
            suffix = candidate.stem.removeprefix("v")
            if len(suffix) != 4 or not suffix.isdigit() or int(suffix) < 1:
                raise ValueError("Orphan authority version is malformed")
            versions.append(int(suffix))
    version = max(versions, default=0) + 1
    return version, root / f"v{version:04d}.json"


def _pid_dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError as error:
        if getattr(error, "winerror", None) in {87, 1168}:
            return True
        raise
    return False


def _reparse_verdicts(response: str, item: Mapping[str, Any], cell: Mapping[str, Any]) -> list[dict[str, Any]]:
    runner = _runner()
    payload = runner._parse_model_json(response)
    artifact_text = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig")
    context_texts = [Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]]
    return runner._normalize_batch(
        payload,
        expected_ids=[str(question_id) for question_id in _rendered_prompt(item, str(cell["arm"]))[1]],
        artifact_id=str(item["item_id"]),
        bundle_id="prose.short_story",
        judge_id=f"{PROVIDER}:{MODEL}",
        run_id=f"preface-pilot-{cell['sequence']:04d}",
        artifact_text=artifact_text,
        context_texts=context_texts,
    )


def _validate_completed_terminal(terminal_path: Path, cell: Mapping[str, Any], private_root: Path) -> dict[str, Any]:
    terminal = _json_object(terminal_path)
    item = _item(private_root, str(cell["item_id"]))
    response = terminal.get("response")
    provider = terminal.get("provider_record")
    reported = provider.get("reported") if isinstance(provider, Mapping) else None
    verdicts = terminal.get("verdicts")
    if terminal.get("status") != "completed" or terminal.get("cell") != cell or not isinstance(response, str) or terminal.get("response_sha256") != _sha256(response) or not isinstance(reported, Mapping) or terminal.get("provider_record_sha256") != _sha256(_canonical(provider)) or reported.get("provider") != "openai" or reported.get("model") != MODEL or reported.get("reasoning_effort") != REASONING or not isinstance(reported.get("session_id"), str) or not reported["session_id"] or terminal.get("session_id_sha256") != _sha256(reported["session_id"]) or not isinstance(verdicts, list) or terminal.get("verdicts_sha256") != _sha256(_canonical(verdicts)):
        raise ValueError("Private completed terminal lacks valid provider/session/response/verdict evidence")
    try:
        reparsed = _reparse_verdicts(response, item, cell)
    except Exception as error:
        raise ValueError("Private completed terminal raw response cannot be reparsed and normalized") from error
    if verdicts != reparsed:
        raise ValueError("Private completed terminal verdicts do not exactly match raw-response normalization")
    return terminal


def _completed(work: Path, schedule: Sequence[Mapping[str, Any]], private_root: Path) -> list[dict[str, Any]]:
    records = _rows(work / PUBLIC_JOURNAL)
    completed: list[dict[str, Any]] = []
    sessions = _capacity_session_commitments(work, private_root)
    index = 0
    while index < len(records):
        if index + 1 >= len(records):
            raise ValueError("Unresolved scored attempt intent; never resend it")
        intent, terminal = records[index:index + 2]
        expected = schedule[len(completed)] if len(completed) < len(schedule) else None
        if expected is None or intent != {"event": "attempt-intent", **expected}:
            raise ValueError("Scored attempt plan drifted or reordered")
        if terminal.get("event") == "zero_contact_proved":
            if terminal != {"event": "zero_contact_proved", "sequence": expected["sequence"], "prompt_sha256": expected["prompt_sha256"], "private_attempt_intent_sha256": terminal.get("private_attempt_intent_sha256")} or not _is_sha256(terminal.get("private_attempt_intent_sha256")):
                raise ValueError("Zero-contact orphan adjudication is malformed")
            index += 2
            continue
        if terminal.get("event") != "completed" or terminal.get("sequence") != expected["sequence"] or terminal.get("prompt_sha256") != expected["prompt_sha256"] or not _is_sha256(terminal.get("private_terminal_sha256")) or not _is_sha256(terminal.get("provider_record_sha256")) or not _is_sha256(terminal.get("session_id_sha256")) or not _is_sha256(terminal.get("verdicts_sha256")):
            raise ValueError("Completed scored attempt is malformed")
        private_terminal = private_root / PRIVATE_CELLS / f"{expected['sequence']:04d}" / "terminal.json"
        if not private_terminal.is_file() or _sha256(private_terminal.read_bytes()) != terminal["private_terminal_sha256"]:
            raise ValueError("Completed scored attempt private evidence drifted")
        private_value = _validate_completed_terminal(private_terminal, expected, private_root)
        if terminal["provider_record_sha256"] != private_value["provider_record_sha256"] or terminal["session_id_sha256"] != private_value["session_id_sha256"] or terminal["verdicts_sha256"] != private_value["verdicts_sha256"]:
            raise ValueError("Public completed commitments do not bind private provider/session/verdict evidence")
        if terminal["session_id_sha256"] in sessions:
            raise ValueError("Fresh-session identity was reused")
        sessions.add(terminal["session_id_sha256"])
        completed.append(dict(expected))
        index += 2
    return completed


def _scored_session_commitments(work: Path) -> set[str]:
    return {
        str(row["session_id_sha256"])
        for row in _rows(work / PUBLIC_JOURNAL)
        if row.get("event") == "completed" and _is_sha256(row.get("session_id_sha256"))
    }


def _capacity_schema(private_root: Path) -> Path:
    path = private_root / PRIVATE_CAPACITY / "capacity-response.schema.json"
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["ready"],
        "properties": {"ready": {"type": "boolean"}},
    }
    _atomic_json(path, schema)
    return path


def _capacity_public_path(work: Path, sequence: int, version: int) -> Path:
    if type(version) is not int or version < 1:
        raise ValueError("Capacity receipt version must be a positive integer")
    return work / f"capacity-preflight-{sequence:04d}-v{version:04d}.json"


def _capacity_paths(work: Path, sequence: int) -> list[tuple[int, Path]]:
    matches: list[tuple[int, Path]] = []
    for path in work.glob(f"capacity-preflight-{sequence:04d}-v*.json"):
        suffix = path.stem.removeprefix(f"capacity-preflight-{sequence:04d}-v")
        if len(suffix) == 4 and suffix.isdigit() and int(suffix) > 0:
            matches.append((int(suffix), path))
        else:
            raise ValueError("Capacity receipt filename is malformed")
    return sorted(matches)


def _capacity_attempt_versions(private_root: Path, sequence: int) -> list[int]:
    root = private_root / PRIVATE_CAPACITY / f"{sequence:04d}"
    if not root.exists():
        return []
    if not root.is_dir():
        raise ValueError("Capacity attempt root is malformed")
    versions = []
    for path in root.iterdir():
        if not path.is_dir() or not re.fullmatch(r"v\d{4}", path.name) or int(path.name[1:]) < 1:
            raise ValueError("Capacity attempt version directory is malformed")
        versions.append(int(path.name[1:]))
    return sorted(versions)


def _capacity_attempt_root(private_root: Path, sequence: int, version: int) -> Path:
    if type(version) is not int or version < 1:
        raise ValueError("Capacity attempt version must be a positive integer")
    return private_root / PRIVATE_CAPACITY / f"{sequence:04d}" / f"v{version:04d}"


def _adjudicate_zero_contact_capacity_orphan(work: Path, private_root: Path, schedule: Sequence[Mapping[str, Any]], sequence: int) -> None:
    """Seal only a dead, pre-dispatch capacity attempt so a later version can run."""
    claim_path = work / CLAIM
    if not claim_path.exists():
        return
    claim = _claim_value(claim_path)
    if not _pid_dead(int(claim["pid"])):
        raise ValueError("Exclusive epoch claim exists; stop without duplicate dispatch")
    records = _rows(work / PUBLIC_JOURNAL)
    completed = _completed(work, schedule, private_root)
    expected = schedule[len(completed)] if len(completed) < len(schedule) else None
    if expected is None or int(expected["sequence"]) != sequence:
        raise ValueError("Dead capacity claim does not bind the current scored cell")
    journal_path = work / PUBLIC_JOURNAL
    journal_bytes = journal_path.read_bytes() if journal_path.exists() else b""
    if claim["pre_intent_journal_sha256"] != _sha256(journal_bytes):
        raise ValueError("Dead capacity claim does not bind the current journal prefix")
    receipt_versions = {version for version, _ in _capacity_paths(work, sequence)}
    versions = [version for version in _capacity_attempt_versions(private_root, sequence) if version not in receipt_versions]
    if len(versions) != 1:
        raise ValueError("Dead capacity claim lacks one uniquely recoverable private attempt")
    version = versions[0]
    destination = _capacity_attempt_root(private_root, sequence, version)
    attempt = destination / "attempt-intent.json"
    if not attempt.is_file() or (destination / "terminal.json").exists() or (destination / "dispatch-start.json").exists():
        raise ValueError("Capacity contact cannot be disproved; preserve the orphan without retry")
    responses = destination / "responses"
    if responses.exists() and any(responses.iterdir()):
        raise ValueError("Capacity contact cannot be disproved; preserve the orphan without retry")
    claim_sha256 = _sha256(claim_path.read_bytes())
    _cleanup_stale_orphan_claim(work, stale_claim_sha256=claim_sha256)
    recovery_claim = _orphan_claim(work, claim_sha256)
    try:
        if not claim_path.is_file() or _sha256(claim_path.read_bytes()) != claim_sha256:
            raise ValueError("Stale capacity claim changed during orphan adjudication")
        attempt_value = _json_object(attempt)
        if attempt_value.get("format_version") != 1 or attempt_value.get("sequence") != sequence or attempt_value.get("version") != version or attempt_value.get("status") != "started" or attempt_value.get("kind") != "unscored_capacity_preflight" or not _is_sha256(attempt_value.get("prompt_sha256")):
            raise ValueError("Dead capacity claim private intent is malformed")
        private_authority = destination / "zero-contact-authority.json"
        public_authority = work / f"capacity-zero-contact-{sequence:04d}-v{version:04d}.json"
        authority = {"format_version": 1, "status": "zero_contact_proved", "sequence": sequence, "version": version, "claim_sha256": claim_sha256, "journal_prefix_sha256": _sha256(journal_bytes), "private_attempt_intent_sha256": _sha256(attempt.read_bytes()), "contact_state": "dispatch-start.json absent and responses empty"}
        _atomic_json(private_authority, authority)
        _atomic_json(public_authority, {key: value for key, value in authority.items() if key != "claim_sha256"})
        claim_path.unlink()
    finally:
        recovery_claim.unlink(missing_ok=True)


def _zero_contact_capacity_authority(work: Path, private_root: Path, sequence: int, version: int) -> bool:
    private_authority = _capacity_attempt_root(private_root, sequence, version) / "zero-contact-authority.json"
    public_authority = work / f"capacity-zero-contact-{sequence:04d}-v{version:04d}.json"
    if not private_authority.is_file() or not public_authority.is_file():
        return False
    private_value = _json_object(private_authority)
    public_value = _json_object(public_authority)
    expected_private = {"format_version", "status", "sequence", "version", "claim_sha256", "journal_prefix_sha256", "private_attempt_intent_sha256", "contact_state"}
    expected_public = expected_private - {"claim_sha256"}
    journal_path = work / PUBLIC_JOURNAL
    journal_bytes = journal_path.read_bytes() if journal_path.exists() else b""
    return set(private_value) == expected_private and set(public_value) == expected_public and private_value["format_version"] == 1 and private_value["status"] == "zero_contact_proved" and private_value["sequence"] == sequence and private_value["version"] == version and _is_sha256(private_value.get("claim_sha256")) and private_value.get("journal_prefix_sha256") == _sha256(journal_bytes) and _is_sha256(private_value.get("private_attempt_intent_sha256")) and private_value["contact_state"] == "dispatch-start.json absent and responses empty" and public_value == {key: value for key, value in private_value.items() if key != "claim_sha256"}


def _validate_capacity_receipt(path: Path, sequence: int, private_root: Path) -> dict[str, Any]:
    value = _json_object(path)
    expected = {"format_version", "study_id", "sequence", "version", "status", "observed_at", "provider", "prompt_sha256", "response_sha256", "provider_record_sha256", "session_id_sha256", "private_terminal_sha256"}
    version = value.get("version")
    if set(value) != expected or value.get("format_version") != 1 or value.get("study_id") != contract()["study_id"] or value.get("sequence") != sequence or type(version) is not int or version < 1 or path != _capacity_public_path(path.parent, sequence, version) or value.get("status") != "ready" or value.get("provider") != {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING} or not all(_is_sha256(value.get(key)) for key in ("prompt_sha256", "response_sha256", "provider_record_sha256", "session_id_sha256", "private_terminal_sha256")):
        raise ValueError("Capacity preflight evidence drifted")
    attempt_root = _capacity_attempt_root(private_root.resolve(), sequence, version)
    terminal_path = attempt_root / "terminal.json"
    terminal = _json_object(terminal_path)
    attempt = _json_object(attempt_root / "attempt-intent.json")
    response = terminal.get("response")
    try:
        ready_payload = json.loads(response) if isinstance(response, str) else None
    except json.JSONDecodeError:
        ready_payload = None
    if _sha256(terminal_path.read_bytes()) != value["private_terminal_sha256"] or terminal.get("status") != "ready" or terminal.get("prompt_sha256") != value["prompt_sha256"] or terminal.get("response_sha256") != value["response_sha256"] or not isinstance(response, str) or _sha256(response) != value["response_sha256"] or ready_payload != {"ready": True} or attempt.get("prompt_sha256") != value["prompt_sha256"] or _sha256(_canonical(terminal.get("provider_record"))) != value["provider_record_sha256"]:
        raise ValueError("Capacity receipt does not bind its private terminal evidence")
    provider_record = terminal.get("provider_record")
    reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None
    if not isinstance(reported, Mapping) or reported.get("model") != MODEL or reported.get("provider") != "openai" or reported.get("reasoning_effort") != REASONING or not isinstance(reported.get("session_id"), str) or not reported["session_id"] or value["session_id_sha256"] != _sha256(reported["session_id"]):
        raise ValueError("Capacity receipt lacks attested Codex provider settings")
    try:
        observed = datetime.fromisoformat(str(value["observed_at"]))
    except ValueError as error:
        raise ValueError("Capacity preflight timestamp is invalid") from error
    if observed.tzinfo is None:
        raise ValueError("Capacity preflight timestamp must be timezone-aware")
    return value


def _latest_capacity_receipt(work: Path, sequence: int, private_root: Path) -> tuple[Path, dict[str, Any]]:
    choices = _capacity_paths(work, sequence)
    if not choices:
        raise ValueError("No capacity preflight receipt exists for the next scored cell")
    version, path = choices[-1]
    receipt = _validate_capacity_receipt(path, sequence, private_root)
    if receipt["version"] != version:
        raise ValueError("Capacity receipt filename/version binding drifted")
    return path, receipt


def _capacity_session_commitments(work: Path, private_root: Path) -> set[str]:
    sessions: set[str] = set()
    for path in sorted(work.glob("capacity-preflight-*.json")):
        match = re.fullmatch(r"capacity-preflight-(\d{4})-v(\d{4})\.json", path.name)
        if match is None:
            raise ValueError("Unexpected capacity receipt name")
        receipt = _validate_capacity_receipt(path, int(match.group(1)), private_root)
        session = str(receipt["session_id_sha256"])
        if session in sessions:
            raise ValueError("Capacity preflight session identity was reused")
        sessions.add(session)
    return sessions


def _parse_capacity(path: Path, sequence: int, private_root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    value = _validate_capacity_receipt(path, sequence, private_root)
    observed = datetime.fromisoformat(str(value["observed_at"]))
    current = now or datetime.now(UTC)
    if observed > current + timedelta(seconds=30) or current - observed > CAPACITY_MAX_AGE:
        raise ValueError("Capacity preflight is not fresh enough for a scored send")
    return value


def run_capacity_preflight(work: Path, private_root: Path, *, allow_remote: bool, timeout: float = 120.0) -> dict[str, Any]:
    """Make exactly one unscored Codex capacity check, then seal its evidence."""
    root, private = work.resolve(), private_root.resolve()
    _verify(root, private)
    if not allow_remote:
        raise ValueError("Capacity preflight uses Codex; pass --allow-remote after reviewing its empty-content disclosure")
    _, schedule = _verify(root, private)
    _cleanup_stale_orphan_claim(root)
    completed = _completed(root, schedule, private)
    if len(completed) == len(schedule):
        return {"provider_calls": 0, "scored_provider_calls": 0, "status": "complete"}
    sequence = int(schedule[len(completed)]["sequence"])
    receipt_versions = {version for version, _ in _capacity_paths(root, sequence)}
    has_unadjudicated_capacity_attempt = any(version not in receipt_versions for version in _capacity_attempt_versions(private, sequence))
    if (root / CLAIM).exists() and has_unadjudicated_capacity_attempt:
        _adjudicate_zero_contact_capacity_orphan(root, private, schedule, sequence)
    _cleanup_completed_epoch_claim(root, private, schedule)
    existing = _capacity_paths(root, sequence)
    known_versions = [version for version, _ in existing] + _capacity_attempt_versions(private, sequence)
    version = max(known_versions, default=0) + 1
    if not existing and known_versions and not all(_zero_contact_capacity_authority(root, private, sequence, prior_version) for prior_version in known_versions):
        raise ValueError("A prior capacity attempt has provider-contact or terminal evidence; do not renew it")
    if existing:
        _, prior = _latest_capacity_receipt(root, sequence, private)
        try:
            _parse_capacity(existing[-1][1], sequence, private)
        except ValueError as error:
            if "not fresh enough" not in str(error):
                raise
        else:
            raise ValueError("Latest capacity receipt is still fresh; do not create a duplicate preflight")
        if prior["version"] != version - 1:
            raise ValueError("Capacity receipt version sequence drifted")
    public_path = _capacity_public_path(root, sequence, version)
    attempt_root = _capacity_attempt_root(private, sequence, version)
    terminal = attempt_root / "terminal.json"
    if public_path.exists() or attempt_root.exists():
        raise ValueError("Capacity preflight version already has private or public evidence; do not retry it")
    claim = _claim(root, journal=root / PUBLIC_JOURNAL)
    settled = False
    try:
        prompt = "Return exactly this JSON object and nothing else: {\"ready\": true}. This is an unscored capacity preflight; do not evaluate any writing."
        disclosure = {"event": "unscored_capacity_preflight_disclosure", "destination": "Codex CLI -> authenticated OpenAI service", "outbound_content": "Only the fixed no-writing capacity prompt", "prompt_sha256": _sha256(prompt), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}}
        _append(root / PUBLIC_DISCLOSURES, {**disclosure, "sequence": sequence, "version": version})
        attempt = attempt_root / "attempt-intent.json"
        _atomic_json(attempt, {"format_version": 1, "sequence": sequence, "version": version, "status": "started", "kind": "unscored_capacity_preflight", "prompt": prompt, "prompt_sha256": _sha256(prompt), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}})
        capacity_schema = _capacity_schema(private)
        runner = _runner()
        try:
            _atomic_json(attempt_root / "dispatch-start.json", {"format_version": 1, "sequence": sequence, "version": version, "claim_sha256": _sha256(claim.read_bytes()), "prompt_sha256": _sha256(prompt), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}})
            response, provider_record = runner._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=attempt_root, response_schema=capacity_schema, batch_number=1, timeout=timeout, attempt_number=1)
            parsed = json.loads(response)
            if parsed != {"ready": True}:
                raise ValueError("Capacity preflight response did not attest ready")
            status = "ready"
            error = None
        except Exception as exc:
            response, provider_record, status, error = "", None, "failed", str(exc)
        terminal_value = {"format_version": 1, "status": status, "prompt_sha256": _sha256(prompt), "response": response, "response_sha256": _sha256(response), "provider_record": provider_record, "error_sha256": _sha256(error) if error is not None else None}
        _atomic_json(terminal, terminal_value)
        if status != "ready":
            settled = True
            raise ValueError("Capacity preflight failed; this root is sealed without a scored send")
        reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None
        session_id = reported.get("session_id") if isinstance(reported, Mapping) else None
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Capacity preflight lacks a provider session ID")
        public = {"format_version": 1, "study_id": contract()["study_id"], "sequence": sequence, "version": version, "status": "ready", "observed_at": datetime.now(UTC).isoformat(), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "prompt_sha256": _sha256(prompt), "response_sha256": _sha256(response), "provider_record_sha256": _sha256(_canonical(provider_record)), "session_id_sha256": _sha256(session_id), "private_terminal_sha256": _sha256(terminal.read_bytes())}
        _atomic_json(public_path, public)
        settled = True
        return {"provider_calls": 1, "scored_provider_calls": 0, "sequence": sequence, "version": version, "status": "ready"}
    finally:
        if settled:
            claim.unlink(missing_ok=True)


def _item(private_root: Path, item_id: str) -> dict[str, Any]:
    private = _private_manifest(private_root)
    matching = [item for item in private["items"] if item["item_id"] == item_id]
    if len(matching) != 1:
        raise ValueError("Scheduled item is not uniquely bound by the private manifest")
    return matching[0]


def _disclosure(cell: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    prompt, question_ids, question_payload_sha256 = _rendered_prompt(item, str(cell["arm"]))
    if _sha256(prompt) != cell["prompt_sha256"] or len(prompt.encode("utf-8")) != cell["prompt_bytes"] or _sha256(_canonical(question_ids)) != cell["question_ids_sha256"] or question_payload_sha256 != cell["compiled_question_payload_sha256"]:
        raise ValueError("Exact rendered-prompt or question binding drifted")
    return {
        "event": "scored_outbound_disclosure",
        "sequence": cell["sequence"],
        "destination": "Codex CLI -> authenticated OpenAI service",
        "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING},
        "cell": {key: cell[key] for key in ("sequence", "item_id", "arm", "fresh_session", "prompt_sha256", "prompt_bytes", "question_ids_sha256", "question_count", "compiled_question_payload_sha256")},
        "outbound_artifacts": _safe_item(item),
        "outbound_content": "The exact private rendered prompt contains the frozen artifact, contexts, full HBQ question sequence, and the treatment preface. Actual provenance is not sent.",
        "human_judgment": False,
        "paid_api": False,
    }


def execute_one(work: Path, private_root: Path, *, allow_remote: bool = False, timeout: float = 3600.0, now: datetime | None = None) -> dict[str, Any]:
    """Run at most one scored cell. Any unresolved attempt permanently stops dispatch."""
    root, private = work.resolve(), private_root.resolve()
    _verify(root, private)
    if not allow_remote:
        raise ValueError("This executor sends disclosed writing to Codex; pass --allow-remote after review")
    _, schedule = _verify(root, private)
    _cleanup_stale_orphan_claim(root)
    _cleanup_completed_epoch_claim(root, private, schedule)
    claim = _claim(root, journal=root / PUBLIC_JOURNAL)
    settled = False
    try:
        _, schedule = _verify(root, private)
        done = _completed(root, schedule, private)
        known_sessions = _capacity_session_commitments(root, private) | _scored_session_commitments(root)
        if len(done) == len(schedule):
            settled = True
            return {"provider_calls": 0, "completed_cells": len(done), "remaining_cells": 0}
        cell = schedule[len(done)]
        capacity_path, _ = _latest_capacity_receipt(root, int(cell["sequence"]), private)
        capacity = _parse_capacity(capacity_path, int(cell["sequence"]), private, now=now)
        item = _item(private, str(cell["item_id"]))
        prompt, question_ids, _ = _rendered_prompt(item, str(cell["arm"]))
        disclosure = _disclosure(cell, item)
        _append(root / PUBLIC_DISCLOSURES, disclosure)
        _append(root / PUBLIC_JOURNAL, {"event": "attempt-intent", **cell})
        destination = private / PRIVATE_CELLS / f"{cell['sequence']:04d}"
        claim_sha256 = _sha256(claim.read_bytes())
        _atomic_json(destination / "attempt-intent.json", {"format_version": 1, "cell": cell, "claim_sha256": claim_sha256, "rendered_prompt": prompt, "rendered_prompt_sha256": _sha256(prompt), "response_schema": _fingerprint(SCHEMA_PATH, reveal_path=True), "capacity_preflight_sha256": _sha256(_canonical(capacity)), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}})
        runner = _runner()
        try:
            _atomic_json(destination / "dispatch-start.json", {"format_version": 1, "sequence": cell["sequence"], "claim_sha256": claim_sha256, "prompt_sha256": cell["prompt_sha256"], "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}})
            response, provider_record = runner._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=destination, response_schema=SCHEMA_PATH, batch_number=1, timeout=timeout, attempt_number=1)
            verdicts = _reparse_verdicts(response, item, cell)
            reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None
            session_id = reported.get("session_id") if isinstance(reported, Mapping) else None
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("Codex did not attest a fresh provider session ID")
            if _sha256(session_id) in known_sessions:
                raise ValueError("Provider session ID was already committed by this pilot")
            terminal = {"format_version": 1, "status": "completed", "cell": cell, "response": response, "response_sha256": _sha256(response), "provider_record": provider_record, "provider_record_sha256": _sha256(_canonical(provider_record)), "session_id_sha256": _sha256(session_id), "verdicts": verdicts, "verdicts_sha256": _sha256(_canonical(verdicts))}
            _atomic_json(destination / "terminal.json", terminal)
            public_terminal = {"event": "completed", "sequence": cell["sequence"], "prompt_sha256": cell["prompt_sha256"], "private_terminal_sha256": _sha256((destination / "terminal.json").read_bytes()), "provider_record_sha256": terminal["provider_record_sha256"], "session_id_sha256": terminal["session_id_sha256"], "verdicts_sha256": terminal["verdicts_sha256"]}
            _append(root / PUBLIC_JOURNAL, public_terminal)
            settled = True
            return {"provider_calls": 1, "scored_provider_calls": 1, "sequence": cell["sequence"], "completed_cells": len(done) + 1, "remaining_cells": len(schedule) - len(done) - 1}
        except Exception as error:
            terminal = {"format_version": 1, "status": "terminal_failure_or_uncertain", "cell": cell, "error_sha256": _sha256(str(error)), "error": str(error)}
            _atomic_json(destination / "terminal.json", terminal)
            _append(root / PUBLIC_JOURNAL, {"event": "terminal_failure_or_uncertain", "sequence": cell["sequence"], "prompt_sha256": cell["prompt_sha256"], "private_terminal_sha256": _sha256((destination / "terminal.json").read_bytes())})
            settled = True
            raise RuntimeError("Scored cell sealed after terminal or uncertain state; do not resend") from error
    finally:
        if settled:
            claim.unlink(missing_ok=True)


def adjudicate_orphan(work: Path, private_root: Path) -> dict[str, Any]:
    """Resolve only a provably zero-contact gap or an already-complete private terminal."""
    root, private = work.resolve(), private_root.resolve()
    _, schedule = _verify(root, private)
    records = _rows(root / PUBLIC_JOURNAL)
    if not records or len(records) % 2 == 0:
        _cleanup_stale_orphan_claim(root)
        _cleanup_completed_epoch_claim(root, private, schedule)
        raise ValueError("No orphan scored attempt is awaiting offline adjudication")
    intent = records[-1]
    completed_count = 0
    for index in range(0, len(records) - 1, 2):
        prior_intent, prior_terminal = records[index:index + 2]
        expected_prior = schedule[completed_count] if completed_count < len(schedule) else None
        if expected_prior is None or prior_intent != {"event": "attempt-intent", **expected_prior}:
            raise ValueError("Prior orphan journal prefix drifted")
        if prior_terminal.get("event") == "completed":
            completed_count += 1
        elif prior_terminal.get("event") != "zero_contact_proved":
            raise ValueError("Prior orphan journal prefix is not adjudicated")
    expected = schedule[completed_count] if completed_count < len(schedule) else None
    if expected is None or intent != {"event": "attempt-intent", **expected}:
        raise ValueError("Orphan intent does not bind the next frozen cell")
    claim_path = root / CLAIM
    claim = _claim_value(claim_path)
    if not _pid_dead(int(claim["pid"])):
        raise ValueError("Orphan claim PID is still live; recovery would race dispatch")
    claim_sha256 = _sha256(claim_path.read_bytes())
    _cleanup_stale_orphan_claim(root, stale_claim_sha256=claim_sha256)
    recovery_claim = _orphan_claim(root, claim_sha256)
    try:
        if not claim_path.is_file() or _sha256(claim_path.read_bytes()) != claim_sha256:
            raise ValueError("Stale epoch claim changed during orphan adjudication")
        prior_bytes = b"".join(_canonical(row) + b"\n" for row in records[:-1])
        if claim["pre_intent_journal_sha256"] != _sha256(prior_bytes):
            raise ValueError("Orphan claim does not bind the exact journal state before intent")
        destination = private / PRIVATE_CELLS / f"{expected['sequence']:04d}"
        attempt = destination / "attempt-intent.json"
        terminal_path = destination / "terminal.json"
        if not attempt.is_file():
            raise ValueError("Orphan private attempt intent is missing")
        attempt_value = _json_object(attempt)
        if attempt_value.get("cell") != expected or attempt_value.get("claim_sha256") != claim_sha256:
            raise ValueError("Orphan private attempt does not bind its claim and cell")
        recovery_version, authority_path = _next_orphan_authority_path(root, int(expected["sequence"]))
        if terminal_path.is_file():
            terminal = _validate_completed_terminal(terminal_path, expected, private)
            existing_sessions = _capacity_session_commitments(root, private) | _scored_session_commitments(root)
            if terminal["session_id_sha256"] in existing_sessions:
                raise ValueError("Recovered private output reuses a globally committed provider session")
            authority = {"format_version": 1, "status": "completed_private_output_adjudicated", "sequence": expected["sequence"], "recovery_version": recovery_version, "claim_sha256": claim_sha256, "private_terminal_sha256": _sha256(terminal_path.read_bytes())}
            _atomic_json(authority_path, authority)
            _append(root / PUBLIC_JOURNAL, {"event": "completed", "sequence": expected["sequence"], "prompt_sha256": expected["prompt_sha256"], "private_terminal_sha256": authority["private_terminal_sha256"], "provider_record_sha256": terminal["provider_record_sha256"], "session_id_sha256": terminal["session_id_sha256"], "verdicts_sha256": terminal["verdicts_sha256"]})
            claim_path.unlink()
            return {"status": "completed_private_output_adjudicated", "provider_calls": 0, "sequence": expected["sequence"]}
        responses = destination / "responses"
        if (destination / "dispatch-start.json").exists() or (responses.exists() and any(responses.iterdir())):
            raise ValueError("Provider contact cannot be disproved; preserve the orphan without resend")
        authority = {"format_version": 1, "status": "zero_contact_proved", "sequence": expected["sequence"], "recovery_version": recovery_version, "claim_sha256": claim_sha256, "private_attempt_intent_sha256": _sha256(attempt.read_bytes()), "contact_state": "dispatch-start.json absent and responses empty"}
        _atomic_json(authority_path, authority)
        _append(root / PUBLIC_JOURNAL, {"event": "zero_contact_proved", "sequence": expected["sequence"], "prompt_sha256": expected["prompt_sha256"], "private_attempt_intent_sha256": authority["private_attempt_intent_sha256"]})
        claim_path.unlink()
        return {"status": "zero_contact_orphan_adjudicated", "provider_calls": 0, "sequence": expected["sequence"]}
    finally:
        recovery_claim.unlink(missing_ok=True)


def render_next_disclosure(work: Path, private_root: Path) -> dict[str, Any]:
    """Render the exact next private prompt plus its safe outbound disclosure, without dispatch."""
    root, private = work.resolve(), private_root.resolve()
    _, schedule = _verify(root, private)
    done = _completed(root, schedule, private)
    if len(done) == len(schedule):
        return {"provider_calls": 0, "status": "complete"}
    cell = schedule[len(done)]
    item = _item(private, str(cell["item_id"]))
    prompt, _, _ = _rendered_prompt(item, str(cell["arm"]))
    disclosure = _disclosure(cell, item)
    if "actual_origin" in _canonical(disclosure).decode("utf-8") or "source_model" in _canonical(disclosure).decode("utf-8"):
        raise ValueError("Outbound disclosure leaks internal provenance")
    return {"provider_calls": 0, "disclosure": disclosure, "exact_rendered_prompt": prompt}


def settle_offline(work: Path, private_root: Path) -> dict[str, Any]:
    """Seal only a safe settlement readiness record; scoring remains offline work."""
    root, private = work.resolve(), private_root.resolve()
    binding, schedule = _verify(root, private)
    done = _completed(root, schedule, private)
    if len(done) != len(schedule):
        raise ValueError("Offline settlement requires all 24 pilot cells to be complete")
    terminals = []
    for cell in done:
        terminal = _json_object(private / PRIVATE_CELLS / f"{cell['sequence']:04d}" / "terminal.json")
        if terminal.get("status") != "completed" or terminal.get("cell") != cell or not _is_sha256(terminal.get("verdicts_sha256")):
            raise ValueError("Private completed terminal is not settlement-ready")
        terminals.append({"sequence": cell["sequence"], "item_id": cell["item_id"], "arm": cell["arm"], "fresh_session": cell["fresh_session"], "private_terminal_sha256": _sha256((private / PRIVATE_CELLS / f"{cell['sequence']:04d}" / "terminal.json").read_bytes()), "verdicts_sha256": terminal["verdicts_sha256"]})
    capacity_receipts = []
    for cell in done:
        paths = _capacity_paths(root, int(cell["sequence"]))
        if not paths:
            raise ValueError("Completed scored cell lacks required capacity preflight evidence")
        for version, receipt_path in paths:
            receipt = _validate_capacity_receipt(receipt_path, int(cell["sequence"]), private)
            capacity_receipts.append({"sequence": cell["sequence"], "version": version, "receipt_sha256": _sha256(receipt_path.read_bytes()), "private_terminal_sha256": receipt["private_terminal_sha256"]})
    summary = {"format_version": 1, "study_id": contract()["study_id"], "status": "complete_ready_for_offline_settlement", "provider_calls": {"scored": len(terminals), "unscored_capacity_preflights": len(capacity_receipts)}, "binding_sha256": _sha256(_canonical(binding)), "schedule_sha256": _sha256(_canonical(schedule)), "completed_cells": terminals, "capacity_receipts": capacity_receipts, "human_judgment": False, "automatic_analysis": False, "automatic_production_change": False}
    _atomic_json(root / PUBLIC_SETTLEMENT, summary)
    return {"provider_calls": 0, "status": summary["status"], "completed_cells": len(terminals)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path, help="fresh/disjoint public evidence root")
    parser.add_argument("private_root", type=Path, help="disjoint private input and raw-evidence root")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--capacity-preflight", action="store_true")
    parser.add_argument("--execute-one", action="store_true")
    parser.add_argument("--settle-offline", action="store_true")
    parser.add_argument("--adjudicate-orphan", action="store_true")
    parser.add_argument("--render-next-disclosure", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--timeout", type=float, default=3600.0)
    arguments = parser.parse_args()
    chosen = sum(bool(value) for value in (arguments.prepare, arguments.capacity_preflight, arguments.execute_one, arguments.settle_offline, arguments.adjudicate_orphan, arguments.render_next_disclosure))
    if chosen != 1:
        parser.error("choose exactly one action")
    if arguments.prepare:
        result = prepare(arguments.work, arguments.private_root)
    elif arguments.capacity_preflight:
        result = run_capacity_preflight(arguments.work, arguments.private_root, allow_remote=arguments.allow_remote, timeout=arguments.timeout)
    elif arguments.execute_one:
        result = execute_one(arguments.work, arguments.private_root, allow_remote=arguments.allow_remote, timeout=arguments.timeout)
    elif arguments.adjudicate_orphan:
        result = adjudicate_orphan(arguments.work, arguments.private_root)
    elif arguments.render_next_disclosure:
        result = render_next_disclosure(arguments.work, arguments.private_root)
    else:
        result = settle_offline(arguments.work, arguments.private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
