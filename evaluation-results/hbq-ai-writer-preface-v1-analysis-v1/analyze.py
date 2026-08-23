#!/usr/bin/env python3
"""Analyze sealed preface evidence without provider, human, or network calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hbqrs.core import compile_bundle, compiled_questions, load_data, score_bundle  # noqa: E402

ARMS = ("none", "current_full", "strictness_only")
STATES = {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
SHA = set("0123456789abcdef")
COMPATIBILITY_AUTHORITY = HERE / "historical-registry-compatibility.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha_bytes(path.read_bytes())}


def _bound_file(path: Path, expected: Mapping[str, Any], label: str) -> dict[str, Any]:
    """Verify a file fingerprint projected by the sealed parent binding."""
    if set(expected) - {"bytes", "sha256", "path_sha256"}:
        raise ValueError(f"{label} binding has unexpected fields")
    found = binding(path)
    if any(found.get(key) != expected.get(key) for key in ("bytes", "sha256")):
        raise ValueError(f"{label} binding drifted")
    path_digest = expected.get("path_sha256")
    if path_digest is not None and path_digest != sha_bytes(str(path.resolve()).encode("utf-8")):
        raise ValueError(f"{label} bound path drifted")
    return found


def _bound_tree(path: Path, expected: Mapping[str, Any], label: str) -> dict[str, Any]:
    if set(expected) != {"files", "sha256"} or not path.is_dir():
        raise ValueError(f"{label} tree binding is malformed")
    entries = []
    for child in sorted(path.rglob("*")):
        if child.is_file():
            contents = child.read_bytes()
            entries.append({"path": child.relative_to(path).as_posix(), "bytes": len(contents), "sha256": sha_bytes(contents)})
    found = {"files": len(entries), "sha256": sha_bytes(canonical(entries))}
    if found != dict(expected):
        raise ValueError(f"{label} tree binding drifted")
    return found


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON object: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def rows(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSONL: {path.name}") from exc
    if any(not isinstance(value, dict) for value in values):
        raise ValueError(f"JSONL requires objects: {path.name}")
    return values


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def rank(values: Sequence[float]) -> list[float]:
    ordered, result, start = sorted(enumerate(values), key=lambda pair: pair[1]), [0.0] * len(values), 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        value = (start + end + 1) / 2
        for index, _ in ordered[start:end]:
            result[index] = value
        start = end
    return result


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    a, b = statistics.fmean(left), statistics.fmean(right)
    denom = sum((x - a) ** 2 for x in left) * sum((y - b) ** 2 for y in right)
    return None if denom == 0 else sum((x - a) * (y - b) for x, y in zip(left, right)) / math.sqrt(denom)


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return pearson(rank(left), rank(right))


def kendall_tau_b(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    concordant = discordant = tied_left = tied_right = 0
    for i, x in enumerate(left):
        for y in range(i + 1, len(left)):
            a, b = (x > left[y]) - (x < left[y]), (right[i] > right[y]) - (right[i] < right[y])
            if not a and not b:
                continue
            if not a:
                tied_left += 1
            elif not b:
                tied_right += 1
            elif a == b:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt((concordant + discordant + tied_left) * (concordant + discordant + tied_right))
    return None if denominator == 0 else (concordant - discordant) / denominator


def mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def contract() -> dict[str, Any]:
    value = read_object(HERE / "study-contract.json")
    if value.get("study_id") != "hbq-ai-writer-preface-v1-analysis-v1" or value.get("format_version") != 1:
        raise ValueError("Analysis contract identity drifted")
    return value


CONTRACT = contract()


def _aggregate_bytes(snapshot: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load the pinned scoring aggregate, never the unresolved historical tree."""
    authority = read_object(COMPATIBILITY_AUTHORITY)
    historical = authority.get("historical_functional_reconstruction")
    if not isinstance(historical, Mapping) or historical.get("identity") != "functional_reconstruction_not_original_full_tree":
        raise ValueError("Historical registry compatibility authority is malformed")
    aggregate = historical.get("aggregate")
    if not isinstance(aggregate, Mapping) or set(aggregate) != {"path", "bytes", "sha256"}:
        raise ValueError("Historical registry aggregate authority is malformed")
    if snapshot is not None:
        try:
            raw = snapshot.read_bytes()
        except OSError as exc:
            raise ValueError("Historical registry snapshot is unavailable") from exc
    else:
        commit, blob, relative = historical.get("commit"), historical.get("git_blob"), aggregate.get("path")
        if not all(isinstance(value, str) and value for value in (commit, blob, relative)):
            raise ValueError("Historical registry git authority is malformed")
        try:
            resolved = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{commit}:{relative}"], text=True, encoding="utf-8", capture_output=True, check=True).stdout.strip()
            if resolved != blob:
                raise ValueError("Historical registry commit/blob binding drifted")
            raw = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", blob], capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("Historical registry git snapshot is unavailable") from exc
    if {"bytes": len(raw), "sha256": sha_bytes(raw)} != {key: aggregate[key] for key in ("bytes", "sha256")}:
        raise ValueError("Historical registry aggregate binding drifted")
    try:
        modules = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Historical registry aggregate is invalid JSON") from exc
    if not isinstance(modules, list) or len(modules) != historical.get("module_count") or not all(isinstance(module, dict) for module in modules):
        raise ValueError("Historical registry aggregate is not the declared 277-module reconstruction")
    return modules, authority


def _current_additive_modules(historical_modules: Sequence[Mapping[str, Any]], authority: Mapping[str, Any], path: Path | None = None) -> list[dict[str, Any]]:
    """Verify the separately named current additive registry without calling it historical."""
    current = authority.get("current_additive_registry")
    if not isinstance(current, Mapping) or current.get("identity") != "current_additive_registry_not_historical_identity":
        raise ValueError("Current additive registry authority is malformed")
    aggregate, addition = current.get("aggregate"), current.get("addition")
    if not isinstance(aggregate, Mapping) or set(aggregate) != {"path", "bytes", "sha256"} or not isinstance(addition, Mapping):
        raise ValueError("Current additive registry aggregate authority is malformed")
    source = path or ROOT / str(aggregate["path"])
    raw = source.read_bytes()
    if {"bytes": len(raw), "sha256": sha_bytes(raw)} != {key: aggregate[key] for key in ("bytes", "sha256")}:
        raise ValueError("Current additive registry aggregate binding drifted")
    try:
        modules = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Current additive registry aggregate is invalid JSON") from exc
    if not isinstance(modules, list) or len(modules) != current.get("module_count") or not all(isinstance(module, dict) for module in modules):
        raise ValueError("Current additive registry module count drifted")
    historical_by_id = {module.get("module_id"): module for module in historical_modules}
    current_by_id = {module.get("module_id"): module for module in modules}
    if len(historical_by_id) != len(historical_modules) or len(current_by_id) != len(modules):
        raise ValueError("Registry module IDs are not unique")
    addition_id = addition.get("module_id")
    if set(current_by_id) - set(historical_by_id) != {addition_id} or set(historical_by_id) - set(current_by_id) or any(current_by_id[module_id] != module for module_id, module in historical_by_id.items()):
        raise ValueError("Current registry is not the declared exact one-module addition")
    if sha_bytes(canonical(current_by_id.get(addition_id))) != addition.get("canonical_json_sha256"):
        raise ValueError("Current registry addition binding drifted")
    return modules


def _exact_binding(path: Path, expected: Mapping[str, Any], label: str) -> dict[str, Any]:
    found = binding(path)
    if found != dict(expected):
        raise ValueError(f"{label} binding drifted")
    return found


def _load_schedule(path: Path) -> list[dict[str, Any]]:
    schedule = rows(path)
    if len(schedule) != 24 or [value.get("sequence") for value in schedule] != list(range(1, 25)):
        raise ValueError("Original frozen schedule is incomplete or reordered")
    if any(value.get("arm") not in ARMS or value.get("fresh_session") not in (1, 2) or not isinstance(value.get("item_id"), str) for value in schedule):
        raise ValueError("Original frozen schedule has invalid cells")
    return schedule


def _terminal(private: Path, sequence: int, continuation: bool) -> Path:
    base = private / ("suffix-cells" if continuation else "cells") / f"{sequence:04d}" / "terminal.json"
    return base


def _validated_completed(cell: Mapping[str, Any], terminal_path: Path, public_terminal: Mapping[str, Any], expected_ids: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    terminal = read_object(terminal_path)
    if terminal.get("status") != "completed" or terminal.get("cell") != cell or terminal.get("response_sha256") != sha_bytes(str(terminal.get("response", "")).encode("utf-8")):
        raise ValueError("Completed terminal identity or raw-response binding drifted")
    verdicts = terminal.get("verdicts")
    if not isinstance(verdicts, list) or terminal.get("verdicts_sha256") != sha_bytes(canonical(verdicts)):
        raise ValueError("Completed terminal verdict binding drifted")
    ids = [value.get("question_id") for value in verdicts if isinstance(value, Mapping)]
    if len(verdicts) != int(cell["question_count"]) or len(set(ids)) != len(ids) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("Completed terminal question coverage drifted")
    if list(ids) != list(expected_ids) or sha_bytes(canonical(list(expected_ids))) != cell.get("question_ids_sha256"):
        raise ValueError("Completed terminal question IDs or ordering drifted")
    for value in verdicts:
        if not isinstance(value, Mapping) or value.get("verdict") not in STATES or not isinstance(value.get("confidence"), (int, float)):
            raise ValueError("Completed terminal verdict is malformed")
    if public_terminal.get("private_terminal_sha256") != sha_bytes(terminal_path.read_bytes()) or public_terminal.get("verdicts_sha256") != terminal["verdicts_sha256"]:
        raise ValueError("Public/private completed terminal parity drifted")
    return [dict(value) for value in verdicts], terminal


def _load_parent_executor() -> Any:
    pilot_path = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-pilot-executor-v1" / "executor.py"
    spec = importlib.util.spec_from_file_location("preface_pilot_executor_for_analysis", pilot_path)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load sealed parent executor")
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    return parent


def _parent_bindings(original_public: Path, original_private: Path, continuation_public: Path, continuation_private: Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], Any]:
    continuation_contract = read_object(ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-continuation-v1" / "study-contract.json")
    parent = continuation_contract.get("parent")
    if not isinstance(parent, Mapping):
        raise ValueError("Continuation parent contract is malformed")
    parent_executor = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-pilot-executor-v1" / "executor.py"
    parent_contract = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-pilot-executor-v1" / "study-contract.json"
    _exact_binding(parent_executor, {"bytes": binding(parent_executor)["bytes"], "sha256": parent["executor_sha256"]}, "Parent executor")
    _exact_binding(parent_contract, {"bytes": binding(parent_contract)["bytes"], "sha256": parent["contract_sha256"]}, "Parent contract")
    schedule_path, journal_path = original_public / "pilot-schedule.jsonl", original_public / "execution-journal.jsonl"
    schedule = _load_schedule(schedule_path)
    journal_bytes = journal_path.read_bytes()
    if sha_bytes(journal_bytes) != parent["journal_through_cell_17_sha256"]:
        raise ValueError("Original journal binding drifted")
    binding_value = read_object(original_public / "executor-binding.json")
    if sha_bytes((original_public / "executor-binding.json").read_bytes()) != parent["executor_binding_sha256"] or sha_bytes(schedule_path.read_bytes()) != parent["schedule_sha256"]:
        raise ValueError("Original public parent binding drifted")
    terminal17 = _terminal(original_private, 17, False)
    if sha_bytes(terminal17.read_bytes()) != parent["cell_17_terminal_sha256"]:
        raise ValueError("Original cell 17 terminal binding drifted")
    raw_path = original_private / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json"
    if not raw_path.is_file() or sha_bytes(raw_path.read_bytes()) != parent["cell_17_raw_response_sha256"]:
        raise ValueError("Original cell 17 raw-response binding drifted")
    if binding_value.get("study_id") != "hbq-ai-writer-preface-v1-pilot-executor-v1":
        raise ValueError("Original executor binding identity drifted")
    hanna_binding = binding_value.get("hanna_provenance_authority")
    if not isinstance(hanna_binding, Mapping):
        raise ValueError("Original HANNA binding is malformed")
    _bound_file(original_private / "hanna-provenance-authority.json", hanna_binding.get("authority", {}), "HANNA provenance authority")
    projection = hanna_binding.get("projection", {})
    sources = hanna_binding.get("sources", {})
    if not isinstance(projection, Mapping) or not isinstance(sources, Mapping):
        raise ValueError("Original HANNA projection binding is malformed")
    _bound_file(original_private / "hanna-projection.json", projection.get("output", {}), "HANNA projection")
    _bound_file(original_private / "hanna-projection-receipt.json", projection.get("receipt", {}), "HANNA projection receipt")
    _bound_file(original_private / "hanna-authority.csv", sources.get("hanna_source", {}), "HANNA source")
    _bound_file(original_private / "hanna-parent-dataset.csv", sources.get("parent_hanna_dataset", {}), "HANNA parent CSV")
    _bound_file(original_private / "provenance-authority.json", sources.get("provenance_source", {}), "HANNA provenance source")
    compatibility = read_object(COMPATIBILITY_AUTHORITY)
    original_tree = compatibility.get("original_executor_registry_tree")
    if not isinstance(original_tree, Mapping) or binding_value.get("runtime", {}).get("registry") != {key: original_tree.get(key) for key in ("files", "sha256")}:
        raise ValueError("Original executor registry binding is not the declared unresolved historical tree")
    unchanged_bundles = compatibility.get("unchanged_bundles")
    if not isinstance(unchanged_bundles, Mapping) or binding_value.get("runtime", {}).get("bundles") != dict(unchanged_bundles):
        raise ValueError("Original executor bundle binding is not the declared unchanged bundle set")
    _bound_tree(ROOT / "bundles", binding_value.get("runtime", {}).get("bundles", {}), "HBQ bundles")
    _bound_file(original_private / "pilot-inputs.json", binding_value.get("private_manifest", {}), "Pilot input manifest")
    input_bindings = binding_value.get("inputs")
    if not isinstance(input_bindings, list) or len(input_bindings) != 4:
        raise ValueError("Original private input bindings are malformed")
    for item in input_bindings:
        if not isinstance(item, Mapping) or not isinstance(item.get("item_id"), str):
            raise ValueError("Original private input binding is malformed")
        item_root = original_private / "inputs" / str(item["item_id"])
        _bound_file(item_root / "story.txt", item.get("artifact", {}), "Pilot artifact")
        contexts = item.get("contexts")
        if not isinstance(contexts, list) or len(contexts) != 1:
            raise ValueError("Pilot context binding is malformed")
        _bound_file(item_root / "prompt.txt", contexts[0], "Pilot context")
        _bound_file(item_root / "task-contract.json", item.get("task_contract", {}), "Pilot task contract")
    parent_runtime = _load_parent_executor()
    parent_runtime.contract()
    private_manifest = parent_runtime._private_manifest(original_private)
    continuation_binding = read_object(continuation_public / "continuation-binding.json")
    _bound_file(ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-continuation-v1" / "study-contract.json", continuation_binding.get("contract", {}), "Continuation contract")
    _bound_file(ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-continuation-v1" / "executor.py", continuation_binding.get("executor", {}), "Continuation executor")
    _bound_file(parent_executor, continuation_binding.get("parent_executor", {}), "Continuation parent executor")
    if continuation_binding.get("original", {}).get("journal_through_cell_17", {}).get("sha256") != parent["journal_through_cell_17_sha256"]:
        raise ValueError("Continuation binding does not preserve original journal")
    original_terminals = [entry for entry in rows(original_public / "execution-journal.jsonl") if entry.get("event") in {"completed", "terminal_failure_or_uncertain"}]
    if [entry.get("sequence") for entry in original_terminals] != list(range(1, 18)):
        raise ValueError("Original terminal journal ordering or coverage drifted")
    original_terminal_bindings = continuation_binding.get("original", {}).get("cells_1_17")
    if not isinstance(original_terminal_bindings, Mapping) or set(original_terminal_bindings) != {f"{sequence:04d}" for sequence in range(1, 18)}:
        raise ValueError("Continuation binding does not cover original terminal set")
    for event in original_terminals:
        sequence = int(event["sequence"])
        terminal_path = _terminal(original_private, sequence, False)
        terminal = read_object(terminal_path)
        expected_status = "completed" if event.get("event") == "completed" else "terminal_failure_or_uncertain"
        if terminal.get("status") != expected_status or event.get("private_terminal_sha256") != sha_bytes(terminal_path.read_bytes()) or original_terminal_bindings[f"{sequence:04d}"] != sha_bytes(terminal_path.read_bytes()):
            raise ValueError("Original terminal journal/continuation binding parity drifted")
    settlement_path = continuation_public / "offline-settlement.json"
    settlement = read_object(settlement_path)
    if settlement.get("binding_sha256") != sha_bytes(canonical(continuation_binding)) or settlement.get("provider_calls") != 0:
        raise ValueError("Continuation settlement binding or offline boundary drifted")
    repair_terminal = continuation_private / "cell-17-repair" / "quote-only" / "terminal.json"
    if not repair_terminal.is_file() or settlement.get("repair_sensitivity", {}).get("status") != "valid_quote_repair":
        raise ValueError("Continuation repair evidence is missing")
    continuation_journal = rows(continuation_public / "continuation-journal.jsonl")
    declared_suffix = continuation_contract.get("execution", {}).get("suffix_sequences")
    if declared_suffix != list(range(18, 25)):
        raise ValueError("Continuation suffix schedule drifted")
    terminal_events = [entry for entry in continuation_journal if entry.get("event") in {"completed", "terminal_failure_or_uncertain"}]
    if [entry.get("sequence") for entry in terminal_events] != declared_suffix:
        raise ValueError("Continuation terminal journal ordering or coverage drifted")
    terminal_failures = []
    for event in terminal_events:
        sequence = int(event["sequence"])
        terminal_path = _terminal(continuation_private, sequence, True)
        terminal = read_object(terminal_path)
        expected_status = "completed" if event.get("event") == "completed" else "terminal_failure_or_uncertain"
        if terminal.get("status") != expected_status or event.get("private_terminal_sha256") != sha_bytes(terminal_path.read_bytes()):
            raise ValueError("Continuation terminal journal/terminal parity drifted")
        if expected_status != "completed":
            terminal_failures.append(sequence)
    settled_failures = settlement.get("primary_analysis", {}).get("suffix_terminal_failures")
    if settled_failures != terminal_failures:
        raise ValueError("Continuation settlement terminal failure set drifted")
    evidence = {"parent_executor": binding(parent_executor), "parent_contract": binding(parent_contract), "continuation_contract": binding(ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-continuation-v1" / "study-contract.json"), "original_executor_binding": binding(original_public / "executor-binding.json"), "original_schedule": binding(schedule_path), "original_journal": binding(journal_path), "continuation_binding": binding(continuation_public / "continuation-binding.json"), "continuation_journal": binding(continuation_public / "continuation-journal.jsonl"), "continuation_settlement": binding(settlement_path), "terminal_failure_sequences": terminal_failures}
    return schedule, evidence, settlement, private_manifest


def _metadata(original_private: Path, private_manifest: Mapping[str, Any]) -> tuple[dict[str, dict[str, str]], dict[str, float]]:
    authority = private_manifest.get("authority")
    authority_records = authority.get("records") if isinstance(authority, Mapping) else None
    if not isinstance(authority_records, Mapping):
        raise ValueError("Verified HANNA authority records are unavailable")
    result: dict[str, dict[str, str]] = {}
    for executor_id, value in authority_records.items():
        if not isinstance(executor_id, str) or not isinstance(value, Mapping) or not all(isinstance(value.get(key), str) for key in ("actual_origin", "source_model", "matching_stratum", "hanna_item_id")):
            raise ValueError("Verified HANNA authority item is malformed")
        result[executor_id] = {key: str(value[key]) for key in ("actual_origin", "source_model", "matching_stratum", "hanna_item_id")}
    if len(result) != 4:
        raise ValueError("Verified HANNA authority does not bind four pilot inputs")
    labels: dict[str, float] = {}
    with (original_private / "hanna-parent-dataset.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            identifier = row.get("Story ID")
            if identifier not in {value["hanna_item_id"] for value in result.values()}:
                continue
            try:
                ratings = [finite(float(row[name]), f"HANNA {name}") for name in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")]
            except (TypeError, ValueError) as exc:
                raise ValueError("Published HANNA rating is malformed") from exc
            labels[str(identifier)] = statistics.fmean(ratings)
    if len(labels) != 4:
        raise ValueError("Published HANNA labels are not exactly bound for the pilot")
    return result, {item: labels[meta["hanna_item_id"]] for item, meta in result.items()}


def _score(verdicts: list[dict[str, Any]], item_id: str, task: Mapping[str, Any], modules: Any, bundle: Mapping[str, Any]) -> dict[str, float]:
    report = score_bundle(modules, bundle, verdicts, artifact_id=item_id, task_contract=task)
    final = report.get("final_score", {})
    base = report.get("base_score", {})
    return {"final_score": finite(final.get("observed"), "final score"), "base_score": finite(base.get("observed") if isinstance(base, Mapping) else base, "base score"), "coverage": finite(report.get("coverage"), "coverage"), "confidence": finite(report.get("confidence"), "confidence"), "yes_rate_assessed": sum(value["verdict"] == "YES" for value in verdicts if value["verdict"] in {"YES", "NO"}) / max(1, sum(value["verdict"] in {"YES", "NO"} for value in verdicts))}


def _historical_prompt(parent: Any, item: Mapping[str, Any], cell: Mapping[str, Any], modules: Sequence[Mapping[str, Any]], bundle: Mapping[str, Any]) -> list[str]:
    task = read_object(Path(str(item["task_contract"]["path"])))
    compiled = compile_bundle(modules, dict(bundle), task_contract=task)
    role_order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda value: role_order.get(str(value.get("role")), 99))
    ids = [str(question["question"]["id"]) for question in questions]
    runner = parent._runner()
    artifact = runner._read_text_record(Path(str(item["artifact"]["path"])))
    contexts = [runner._read_text_record(Path(str(value["path"]))) for value in item["contexts"]]
    prompt = runner._render_prompt(binary_prompt=parent._binary_prompt_for_arm(str(cell["arm"])), artifact=artifact, contexts=contexts, bundle_id="prose.short_story", artifact_id=str(item["item_id"]), questions=questions, provider=parent.PROVIDER, model=parent.MODEL)
    if sha_bytes(prompt.encode("utf-8")) != cell.get("prompt_sha256") or len(prompt.encode("utf-8")) != cell.get("prompt_bytes") or sha_bytes(canonical(ids)) != cell.get("question_ids_sha256") or sha_bytes(canonical(runner._question_payload(questions))) != cell.get("compiled_question_payload_sha256"):
        raise ValueError("Sealed question IDs, payload, or prompt binding drifted before score math")
    return ids


def _load_records(original_public: Path, original_private: Path, continuation_public: Path, continuation_private: Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], Any]:
    schedule, evidence, settlement, private_manifest = _parent_bindings(original_public, original_private, continuation_public, continuation_private)
    metadata, hanna = _metadata(original_private, private_manifest)
    originals = rows(original_public / "execution-journal.jsonl")
    continuation = rows(continuation_public / "continuation-journal.jsonl")
    events = {int(row["sequence"]): row for row in originals + continuation if row.get("event") == "completed" and isinstance(row.get("sequence"), int)}
    failure_sequences = set(evidence["terminal_failure_sequences"])
    modules, _ = _aggregate_bytes()
    bundle = load_data(ROOT / "bundles" / "prose.short_story.yaml")
    parent = _load_parent_executor()
    expected_ids = {int(cell["sequence"]): _historical_prompt(parent, parent._item(original_private, str(cell["item_id"])), cell, modules, bundle) for cell in schedule}
    records: list[dict[str, Any]] = []
    for cell in schedule:
        sequence = int(cell["sequence"])
        if sequence == 17 or sequence in failure_sequences:
            continue
        event = events.get(sequence)
        terminal_path = _terminal(continuation_private if sequence >= 18 else original_private, sequence, sequence >= 18)
        if event is None or not terminal_path.is_file():
            raise ValueError("A required completed preface cell is missing")
        item = str(cell["item_id"])
        verdicts, terminal = _validated_completed(cell, terminal_path, event, expected_ids[sequence])
        task = read_object(original_private / "inputs" / item / "task-contract.json")
        records.append({"sequence": sequence, "arm": str(cell["arm"]), "session": int(cell["fresh_session"]), "item": item, "metadata": metadata[item], "hanna": hanna[item], "verdicts": verdicts, "metrics": _score(verdicts, item, task, modules, bundle), "terminal_sha256": sha_bytes(terminal_path.read_bytes()), "verdicts_sha256": str(terminal["verdicts_sha256"])})
    if len(records) != 22 or Counter(record["arm"] for record in records) != {"none": 8, "current_full": 8, "strictness_only": 6}:
        raise ValueError("Primary records do not preserve the declared 22-cell design")
    repair = read_object(continuation_private / "cell-17-repair" / "quote-only" / "terminal.json")
    if repair.get("status") != "valid_quote_repair" or repair.get("repair_attempt_id") != "cell17-quote-repair-v1":
        raise ValueError("Cell 17 repair is not a valid quote repair")
    return records, evidence, {"repair_terminal": binding(continuation_private / "cell-17-repair" / "quote-only" / "terminal.json"), "settlement": settlement}, private_manifest


def _repair_substitution(original_public: Path, original_private: Path, continuation_private: Path, private_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Re-normalize the original response with only the sealed repaired leaf replaced."""
    parent = _load_parent_executor()
    raw_path = original_private / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json"
    original = read_object(raw_path)
    repair = read_object(continuation_private / "cell-17-repair" / "quote-only" / "terminal.json")
    repair_response = json.loads(str(repair.get("response", "")))
    raw_rows, repair_rows = original.get("verdicts"), repair_response.get("verdicts") if isinstance(repair_response, Mapping) else None
    if not isinstance(raw_rows, list) or not isinstance(repair_rows, list) or len(repair_rows) != 1:
        raise ValueError("Quote repair payload is malformed")
    leaf = str(repair.get("failed_leaf_id"))
    indexes = [index for index, row in enumerate(raw_rows) if isinstance(row, Mapping) and row.get("question_id") == leaf]
    if len(indexes) != 1 or repair_rows[0].get("question_id") != leaf:
        raise ValueError("Quote repair does not target exactly one original leaf")
    repaired_rows = [dict(row) if isinstance(row, Mapping) else row for row in raw_rows]
    repaired_rows[indexes[0]] = repair_rows[0]
    schedule = _load_schedule(original_public / "pilot-schedule.jsonl")
    cell17 = next(value for value in schedule if value.get("sequence") == 17)
    item = parent._item(original_private, str(cell17["item_id"]))
    try:
        normalized = parent._reparse_verdicts(json.dumps({"verdicts": repaired_rows}, ensure_ascii=False, separators=(",", ":")), item, cell17)
    except Exception:
        return {"record": None, "repaired_leaf_count": 1, "repair_attempt_id": str(repair["repair_attempt_id"]), "whole_cell_substitution_status": "unavailable_additional_unrepaired_validation_failure"}
    expected = repair.get("normalized_verdicts")
    replacement = next(value for value in normalized if value["question_id"] == leaf)
    if not isinstance(expected, list) or len(expected) != 1 or any(replacement.get(key) != expected[0].get(key) for key in ("question_id", "verdict", "confidence", "evidence")):
        raise ValueError("Quote repair normalization does not match sealed repair verdict")
    metadata, hanna = _metadata(original_private, private_manifest)
    modules, _ = _aggregate_bytes()
    bundle = load_data(ROOT / "bundles" / "prose.short_story.yaml")
    item_id = str(cell17["item_id"])
    task = read_object(original_private / "inputs" / item_id / "task-contract.json")
    record = {"sequence": 17, "arm": str(cell17["arm"]), "session": int(cell17["fresh_session"]), "item": item_id, "metadata": metadata[item_id], "hanna": hanna[item_id], "verdicts": normalized, "metrics": _score(normalized, item_id, task, modules, bundle), "terminal_sha256": sha_bytes(raw_path.read_bytes()), "verdicts_sha256": sha_bytes(canonical(normalized))}
    return {"record": record, "repaired_leaf_count": 1, "repair_attempt_id": str(repair["repair_attempt_id"]), "whole_cell_substitution_status": "valid"}


def verify_current_additive_rescoring(original_public: Path, original_private: Path, continuation_public: Path, continuation_private: Path, current_registry: Path | None = None) -> dict[str, int]:
    """Check the named 1.2 addition against historical scoring without relabeling it."""
    records, _, _, _ = _load_records(original_public, original_private, continuation_public, continuation_private)
    historical_modules, authority = _aggregate_bytes()
    current_modules = _current_additive_modules(historical_modules, authority, current_registry)
    bundle = load_data(ROOT / "bundles" / "prose.short_story.yaml")
    for record in records:
        task = read_object(original_private / "inputs" / str(record["item"]) / "task-contract.json")
        if _score(record["verdicts"], str(record["item"]), task, current_modules, bundle) != record["metrics"]:
            raise ValueError("Current additive registry does not preserve historical 22-cell score metrics")
    return {"sealed_cells_with_question_id_payload_prompt_parity": 24, "rescored_completed_cells_with_metric_parity": len(records)}


def _summarize(records: Sequence[Mapping[str, Any]], *, continuation_terminal_failures: Sequence[int], allow_partial_unit: bool = False) -> dict[str, Any]:
    by_item_arm: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_item_arm[(str(record["item"]), str(record["arm"]))].append(record)
    units = []
    for (item, arm), values in sorted(by_item_arm.items()):
        values = sorted(values, key=lambda value: int(value["session"]))
        if len(values) != 2 and not (allow_partial_unit and len(values) == 1):
            continue
        if len({value["session"] for value in values}) != len(values):
            raise ValueError("Duplicate session within an analysis unit")
        ids = [[str(verdict["question_id"]) for verdict in value["verdicts"]] for value in values]
        if any(sequence != ids[0] for sequence in ids[1:]):
            raise ValueError("Repeatability requires identically ordered verdict IDs")
        metrics = {key: statistics.fmean(float(value["metrics"][key]) for value in values) for key in values[0]["metrics"]}
        repeat_agreement = statistics.fmean(sum(a["verdict"] == b["verdict"] for a, b in zip(values[0]["verdicts"], values[1]["verdicts"])) / len(values[0]["verdicts"]) for _ in [0]) if len(values) == 2 else None
        units.append({"item": item, "arm": arm, "origin": values[0]["metadata"]["actual_origin"], "stratum": values[0]["metadata"]["matching_stratum"], "hanna": float(values[0]["hanna"]), "metrics": metrics, "repeatability": repeat_agreement, "leaves": [value["verdicts"] for value in values]})
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        by_arm[unit["arm"]].append(unit)
    arm_summary = {}
    for arm in ARMS:
        values = by_arm[arm]
        intact = [unit["repeatability"] for unit in values if unit["repeatability"] is not None]
        arm_summary[arm] = {"valid_input_count": len(values), "valid_cell_count": sum(len(unit["leaves"]) for unit in values), "equal_input_weight": 1 / len(values) if values else None, "mean_metrics": {key: mean([unit["metrics"][key] for unit in values]) for key in ("final_score", "base_score", "coverage", "confidence", "yes_rate_assessed")}, "same_input_repeatability": mean(intact), "same_input_repeatability_unit_count": len(intact)}
    def contrast(left: str, right: str, subset: Sequence[dict[str, Any]]) -> dict[str, Any]:
        paired = [unit for unit in subset if (unit["item"], right) in by_item_arm and unit["arm"] == left]
        right_units = {unit["item"]: unit for unit in units if unit["arm"] == right}
        return {"eligible_input_count": len(paired), "mean_shift_left_minus_right": {key: mean([unit["metrics"][key] - right_units[unit["item"]]["metrics"][key] for unit in paired]) for key in ("final_score", "base_score", "coverage", "confidence", "yes_rate_assessed")}}
    all_units = list(units)
    contrasts = {"current_full_minus_strictness_only": contrast("current_full", "strictness_only", all_units), "none_minus_strictness_only_descriptive": contrast("none", "strictness_only", all_units), "current_full_minus_none_descriptive": contrast("current_full", "none", all_units)}
    strata = {origin: {arm: {"valid_input_count": len([u for u in units if u["origin"] == origin and u["arm"] == arm]), "mean_final_score": mean([u["metrics"]["final_score"] for u in units if u["origin"] == origin and u["arm"] == arm])} for arm in ARMS} for origin in ("ai_written", "non_ai_written")}
    interaction = {}
    for metric in ("final_score", "base_score", "coverage", "confidence", "yes_rate_assessed"):
        deltas = {}
        for origin in ("ai_written", "non_ai_written"):
            pairs = [unit for unit in units if unit["origin"] == origin and unit["arm"] == "current_full" and (unit["item"], "strictness_only") in by_item_arm]
            right_units = {unit["item"]: unit for unit in units if unit["arm"] == "strictness_only"}
            deltas[origin] = mean([unit["metrics"][metric] - right_units[unit["item"]]["metrics"][metric] for unit in pairs])
        interaction[metric] = None if None in deltas.values() else deltas["ai_written"] - deltas["non_ai_written"]
    flips = {}
    for key, left, right in (("current_full_vs_strictness_only", "current_full", "strictness_only"), ("none_vs_strictness_only", "none", "strictness_only"), ("current_full_vs_none", "current_full", "none")):
        all_session_rates, same_session_rates, different_session_rates = [], [], []
        for unit in units:
            if unit["arm"] != left or (unit["item"], right) not in by_item_arm:
                continue
            other = next(value for value in units if value["item"] == unit["item"] and value["arm"] == right)
            left_sessions = sorted(record["session"] for record in by_item_arm[(unit["item"], left)])
            right_sessions = sorted(record["session"] for record in by_item_arm[(unit["item"], right)])
            if len(left_sessions) != len(unit["leaves"]) or len(right_sessions) != len(other["leaves"]):
                raise ValueError("Cross-arm session geometry drifted")
            for left_session, one in zip(left_sessions, unit["leaves"]):
                for right_session, two in zip(right_sessions, other["leaves"]):
                    if len(one) != len(two) or [row["question_id"] for row in one] != [row["question_id"] for row in two]:
                        raise ValueError("Cross-arm flip metrics require identically ordered verdict IDs")
                    rate = sum(a["verdict"] != b["verdict"] for a, b in zip(one, two)) / len(one)
                    all_session_rates.append(rate)
                    (same_session_rates if left_session == right_session else different_session_rates).append(rate)
        flips[key] = {"all_cross_arm_session_pair_count": len(all_session_rates), "same_session_pair_count": len(same_session_rates), "different_session_pair_count": len(different_session_rates), "mean_leaf_flip_rate_all_cross_arm_sessions": mean(all_session_rates), "mean_leaf_agreement_all_cross_arm_sessions": None if not all_session_rates else 1 - statistics.fmean(all_session_rates)}
    hanna = {arm: {"eligible_input_count": len(by_arm[arm]), "score_vs_hanna_spearman": spearman([unit["metrics"]["final_score"] for unit in by_arm[arm]], [unit["hanna"] for unit in by_arm[arm]]), "score_vs_hanna_kendall_tau_b": kendall_tau_b([unit["metrics"]["final_score"] for unit in by_arm[arm]], [unit["hanna"] for unit in by_arm[arm]])} for arm in ARMS}
    missing = [17, *sorted(set(continuation_terminal_failures))]
    return {"sample": {"analysis_cell_count": len(records), "missing_primary_sequences": missing, "original_terminal_failure_sequences": [17], "continuation_terminal_failure_sequences": sorted(set(continuation_terminal_failures)), "cell_17": "partial_quote_repair_substitution" if allow_partial_unit else "terminal_failure_missing_no_imputation", "repeatability_units": sum(unit["repeatability"] is not None for unit in units), "all_expected_units": 12, "partial_input_units": sum(len(unit["leaves"]) == 1 for unit in units)}, "arms": arm_summary, "canonical_leaf_flips": flips, "contrasts": contrasts, "actual_origin_strata": strata, "actual_origin_by_declared_preface_interaction": {"estimable": True, "current_full_minus_strictness_only_difference_of_origin_effects": interaction}, "hanna_overlap": {"status": "descriptive_exact_published_labels_bound", "metrics": hanna, "not_fresh_human_judgment": True}, "uncertainty": {"pilot_only": True, "no_hypothesis_test_or_automatic_wording_decision": True, "smallest_pairwise_contrast_input_count": min(value["eligible_input_count"] for value in contrasts.values())}}


def _privacy_check(value: Any) -> None:
    forbidden = {"item", "item_id", "question_id", "verdict", "response", "prompt", "path", "session", "session_id", "raw"}
    if isinstance(value, Mapping):
        if set(value) & forbidden:
            raise ValueError("Public analysis would expose private record material")
        for child in value.values():
            _privacy_check(child)
    elif isinstance(value, list):
        for child in value:
            _privacy_check(child)


def _write(output: Path, summary: Mapping[str, Any]) -> None:
    if output.exists():
        raise ValueError("Analysis output must be a new disjoint directory")
    body = canonical(summary) + b"\n"
    manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "files": {"summary.json": {"bytes": len(body), "sha256": sha_bytes(body)}}}
    output.mkdir(parents=True)
    (output / "summary.json").write_bytes(body)
    (output / "manifest.json").write_bytes(canonical(manifest) + b"\n")


def analyze(original_public: Path, original_private: Path, continuation_public: Path, continuation_private: Path, output: Path) -> dict[str, Any]:
    roots = [path.resolve() for path in (original_public, original_private, continuation_public, continuation_private)]
    if any(output.resolve() == root or output.resolve() in root.parents or root in output.resolve().parents for root in roots):
        raise ValueError("Output must be disjoint from sealed evidence roots")
    records, evidence, repair, private_manifest = _load_records(*roots)
    terminal_failures = [int(value) for value in evidence["terminal_failure_sequences"]]
    primary = _summarize(records, continuation_terminal_failures=terminal_failures)
    repaired = _repair_substitution(original_public, original_private, continuation_private, private_manifest)
    sensitivity = {"status": repaired["whole_cell_substitution_status"], "repair_is_not_an_independent_vote": True, "repair_evidence": repair["repair_terminal"], "repaired_leaf_count": repaired["repaired_leaf_count"], "repair_attempt_id_sha256": sha_bytes(repaired["repair_attempt_id"].encode("utf-8")), "analysis": _summarize([*records, repaired["record"]], continuation_terminal_failures=terminal_failures, allow_partial_unit=True) if repaired["record"] is not None else None, "boundary": "The valid leaf repair cannot repair a distinct terminal failure or add a replicate. Whole-cell sensitivity is omitted when independent quote validation finds another unrepaired response defect."}
    summary = {"format_version": 1, "study_id": CONTRACT["study_id"], "analysis_only": True, "automatic_wording_decision": False, "canonical_hbq_registry_unchanged": True, "evidence": evidence, "primary": primary, "repair_sensitivity": sensitivity, "interpretation": "This compact pilot quantifies preface-associated score, coverage, confidence, repeatability, and label-overlap differences while preserving original failures as missing evidence.", "limitations": ["Pilot sample sizes are small.", "Published HANNA labels are historical data, not fresh human judgment.", "The current_full contrast includes the production preface package; it does not isolate one sentence.", "Confidence is reported descriptively and does not reweight canonical HBQ scoring or coverage."] , "privacy": "Aggregate-only: no prose, prompts, raw responses, private paths, item IDs, question IDs, session IDs, or request IDs."}
    _privacy_check(summary)
    _write(output.resolve(), summary)
    verify_output(output)
    return summary


def verify_output(output: Path) -> dict[str, Any]:
    summary_path, manifest_path = output / "summary.json", output / "manifest.json"
    summary, manifest = read_object(summary_path), read_object(manifest_path)
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "files": {"summary.json": binding(summary_path)}}
    if manifest != expected or summary.get("study_id") != CONTRACT["study_id"] or summary.get("automatic_wording_decision") is not False:
        raise ValueError("Public analysis manifest or decision boundary drifted")
    _privacy_check(summary)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-public", required=True, type=Path)
    parser.add_argument("--original-private", required=True, type=Path)
    parser.add_argument("--continuation-public", required=True, type=Path)
    parser.add_argument("--continuation-private", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    analyze(arguments.original_public, arguments.original_private, arguments.continuation_public, arguments.continuation_private, arguments.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
