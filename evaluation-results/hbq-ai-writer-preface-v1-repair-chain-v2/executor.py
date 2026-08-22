"""Sealed quote-only repair chain for the preface pilot's cell-17 sensitivity path."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
CONTINUATION = HERE.parent / "hbq-ai-writer-preface-v1-continuation-v1"
ORIGINAL = HERE.parent / "hbq-ai-writer-preface-v1-pilot-executor-v1"
CONTRACT_PATH = HERE / "study-contract.json"
PUBLIC_BINDING = "repair-chain-binding.json"
PUBLIC_DISCLOSURES = "outbound-disclosures.jsonl"
PUBLIC_JOURNAL = "repair-chain-journal.jsonl"
PUBLIC_SETTLEMENT = "offline-settlement.json"
PRIVATE_ATTEMPTS = "repair-attempts"
CLAIM = "active-repair-claim.json"
MODEL, REASONING, PROVIDER = "gpt-5.6-sol", "high", "codex"
MAX_ADDITIONAL_ATTEMPTS = 3
QUOTE_FAILURE = re.compile(r"Evidence item \d+ for ([a-z0-9_.-]+) has an exact_quote that does not occur verbatim")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON object: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Invalid JSON object: {path.name}")
    return value


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Malformed JSONL: {path.name}")
        result.append(value)
    return result


def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical(value) + b"\n")
    os.replace(temporary, path)


def _append(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as output:
        output.write(_canonical(value) + b"\n")


def _fingerprint(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": _sha(data)}


def _disjoint(*roots: Path) -> bool:
    resolved = [root.resolve() for root in roots]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1:]:
            try:
                left.relative_to(right)
                return False
            except ValueError:
                pass
            try:
                right.relative_to(left)
                return False
            except ValueError:
                pass
    return True


def _continuation() -> Any:
    name = "hbq_ai_writer_preface_continuation_for_repair_chain_v2"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, CONTINUATION / "executor.py")
        if spec is None or spec.loader is None:
            raise ValueError("Continuation executor cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    value = _json(CONTRACT_PATH)
    lineage = value.get("lineage")
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-ai-writer-preface-v1-repair-chain-v2" or not isinstance(lineage, dict):
        raise ValueError("Repair-chain contract drifted")
    required = {
        "original_executor_sha256": ORIGINAL / "executor.py",
        "original_contract_sha256": ORIGINAL / "study-contract.json",
        "continuation_executor_sha256": CONTINUATION / "executor.py",
        "continuation_contract_sha256": CONTINUATION / "study-contract.json",
    }
    for key, path in required.items():
        if lineage.get(key) != _sha(path.read_bytes()):
            raise ValueError("Frozen parent package drifted")
    repair = value.get("repair")
    if not isinstance(repair, dict) or repair.get("max_additional_attempts") != MAX_ADDITIONAL_ATTEMPTS or repair.get("kind") != "quote_only":
        raise ValueError("Repair-chain cap drifted")
    return value


def _require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or _sha(path.read_bytes()) != expected:
        raise ValueError(f"{label} drifted")


def _verify_inputs(original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path) -> Any:
    fixed = contract()["lineage"]
    paths = {
        "original public binding": (original_work / "executor-binding.json", fixed["original_public_binding_sha256"]),
        "original journal": (original_work / "execution-journal.jsonl", fixed["original_journal_sha256"]),
        "original cell 17 terminal": (original_private / "cells" / "0017" / "terminal.json", fixed["original_cell17_terminal_sha256"]),
        "original cell 17 raw response": (original_private / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json", fixed["original_cell17_raw_response_sha256"]),
        "continuation public binding": (continuation_work / "continuation-binding.json", fixed["continuation_public_binding_sha256"]),
        "continuation journal": (continuation_work / "continuation-journal.jsonl", fixed["continuation_journal_sha256"]),
        "continuation settlement": (continuation_work / "offline-settlement.json", fixed["continuation_settlement_sha256"]),
        "first quote repair terminal": (continuation_private / "cell-17-repair" / "quote-only" / "terminal.json", fixed["first_quote_repair_terminal_sha256"]),
    }
    for label, (path, digest) in paths.items():
        _require_hash(path, digest, label)
    continuation = _continuation()
    continuation._verify(continuation_work, continuation_private, original_work, original_private)
    first = _json(continuation_private / "cell-17-repair" / "quote-only" / "terminal.json")
    if first.get("status") != "valid_quote_repair" or first.get("repair_attempt_id") != "cell17-quote-repair-v1":
        raise ValueError("First quote repair is not a sealed valid repair")
    return continuation._parent()


def _binding(original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path) -> dict[str, Any]:
    _verify_inputs(original_work, original_private, continuation_work, continuation_private)
    return {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "contract": _fingerprint(CONTRACT_PATH),
        "executor": _fingerprint(HERE / "executor.py"),
        "lineage": {
            "original_public_binding": _fingerprint(original_work / "executor-binding.json"),
            "original_journal": _fingerprint(original_work / "execution-journal.jsonl"),
            "original_cell17_terminal": _fingerprint(original_private / "cells" / "0017" / "terminal.json"),
            "original_cell17_raw_response": _fingerprint(original_private / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json"),
            "continuation_public_binding": _fingerprint(continuation_work / "continuation-binding.json"),
            "continuation_journal": _fingerprint(continuation_work / "continuation-journal.jsonl"),
            "continuation_settlement": _fingerprint(continuation_work / "offline-settlement.json"),
            "first_quote_repair_terminal": _fingerprint(continuation_private / "cell-17-repair" / "quote-only" / "terminal.json"),
        },
        "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING},
        "original_and_continuation_roots": "read-only evidence; this package never writes them",
    }


def prepare(work: Path, private_root: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path) -> dict[str, Any]:
    roots = tuple(path.resolve() for path in (work, private_root, original_work, original_private, continuation_work, continuation_private))
    if not _disjoint(*roots):
        raise ValueError("Repair-chain roots must be pairwise disjoint")
    root, private = roots[0], roots[1]
    if (root.exists() and any(root.iterdir())) or (private.exists() and any(private.iterdir())):
        raise ValueError("Prepare requires fresh, empty repair-chain roots")
    binding = _binding(*roots[2:])
    root.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    _atomic(root / PUBLIC_BINDING, binding)
    return {"provider_calls": 0, "max_additional_repairs": MAX_ADDITIONAL_ATTEMPTS, "status": "prepared"}


def _verify(work: Path, private_root: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path) -> tuple[Any, dict[str, Any]]:
    roots = tuple(path.resolve() for path in (work, private_root, original_work, original_private, continuation_work, continuation_private))
    if not _disjoint(*roots):
        raise ValueError("Repair-chain roots must remain disjoint")
    expected = _binding(*roots[2:])
    if _json(roots[0] / PUBLIC_BINDING) != expected:
        raise ValueError("Prepared repair-chain binding drifted")
    return _verify_inputs(*roots[2:]), expected


def _original_cell(parent: Any, original_private: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    terminal = _json(original_private / "cells" / "0017" / "terminal.json")
    cell = terminal.get("cell")
    if terminal.get("status") != "terminal_failure_or_uncertain" or not isinstance(cell, dict) or cell.get("sequence") != 17:
        raise ValueError("Original cell 17 drifted")
    payload = _json(original_private / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json")
    verdicts = payload.get("verdicts")
    if not isinstance(verdicts, list) or not all(isinstance(row, dict) and isinstance(row.get("question_id"), str) for row in verdicts):
        raise ValueError("Original cell 17 payload is malformed")
    item = parent._item(original_private, str(cell["item_id"]))
    return cell, item, [dict(row) for row in verdicts]


def _terminal_paths(private: Path) -> list[Path]:
    root = private / PRIVATE_ATTEMPTS
    if not root.exists():
        return []
    directories = sorted(root.iterdir())
    expected_directories = [root / f"{number:02d}" for number in range(1, len(directories) + 1)]
    if directories != expected_directories or any(not path.is_dir() for path in directories):
        raise ValueError("Repair-chain attempts are not a contiguous immutable sequence")
    paths = [path / "terminal.json" for path in directories]
    if any(not path.is_file() for path in paths):
        raise ValueError("Repair-chain has an unsealed private attempt")
    return paths


def _repair_response(terminal: Mapping[str, Any]) -> dict[str, Any]:
    response = terminal.get("response")
    if not isinstance(response, str):
        raise ValueError("Valid repair lacks its raw response")
    payload = json.loads(response)
    rows = payload.get("verdicts") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Valid repair response geometry drifted")
    return dict(rows[0])


def _provider_attestation(terminal: Mapping[str, Any]) -> str:
    provider = terminal.get("provider_record")
    reported = provider.get("reported") if isinstance(provider, Mapping) else None
    session = reported.get("session_id") if isinstance(reported, Mapping) else None
    if not isinstance(provider, Mapping) or terminal.get("provider_record_sha256") != _sha(_canonical(provider)) or not isinstance(reported, Mapping) or reported.get("provider") != "openai" or reported.get("model") != MODEL or reported.get("reasoning_effort") != REASONING or not isinstance(session, str) or not session or terminal.get("session_id_sha256") != _sha(session):
        raise ValueError("Repair terminal lacks an attested Sol/high provider session")
    return _sha(session)


def _attempt_intent(attempt_id: str, metadata: Mapping[str, Any], prompt: str, parent: Any, claim_sha256: str) -> dict[str, Any]:
    return {"format_version": 1, "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "locked": metadata["locked"], "claim_sha256": claim_sha256, "prompt": prompt, "prompt_sha256": _sha(prompt), "response_schema": _fingerprint(parent.SCHEMA_PATH)}


def _disclosure(attempt_id: str, metadata: Mapping[str, Any], prompt: str) -> dict[str, Any]:
    return {"event": "cell_17_quote_repair_disclosure", "destination": "Codex CLI -> authenticated OpenAI service", "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "locked": metadata["locked"], "outbound_content": "Only the next failed leaf, locked original verdict/confidence, artifact, and relevant context; actual provenance is not sent.", "prompt_sha256": _sha(prompt), "paid_api": False, "human_judgment": False}


def _verify_attempt(parent: Any, original_private: Path, root: Path, path: Path) -> dict[str, Any]:
    terminal = _json(path)
    attempt_number = int(path.parent.name)
    attempt_id = f"cell17-quote-repair-chain-v2-{attempt_number:02d}"
    leaf = terminal.get("failed_leaf_id")
    if not isinstance(leaf, str) or terminal.get("repair_attempt_id") != attempt_id:
        raise ValueError("Repair terminal identity is malformed")
    prompt, metadata = _repair_prompt(parent, original_private, leaf)
    intent_path, dispatch_path = path.parent / "attempt-intent.json", path.parent / "dispatch-start.json"
    if not intent_path.is_file() or not dispatch_path.is_file():
        raise ValueError("Repair terminal lacks immutable dispatch evidence")
    intent = _json(intent_path)
    claim_sha256 = intent.get("claim_sha256")
    if not isinstance(claim_sha256, str) or len(claim_sha256) != 64 or intent != _attempt_intent(attempt_id, metadata, prompt, parent, claim_sha256):
        raise ValueError("Repair private attempt intent is malformed or drifted")
    claim_snapshot = path.parent / "claim.json"
    if not claim_snapshot.is_file() or _sha(claim_snapshot.read_bytes()) != claim_sha256:
        raise ValueError("Repair private attempt lacks its exclusive-claim snapshot")
    expected_dispatch = {"format_version": 1, "repair_attempt_id": attempt_id, "claim_sha256": claim_sha256, "prompt_sha256": _sha(prompt), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}}
    if _json(dispatch_path) != expected_dispatch:
        raise ValueError("Repair dispatch evidence is malformed or drifted")
    status = terminal.get("status")
    if status not in {"valid_quote_repair", "invalid_quote_repair", "non_quote_repair_failure", "terminal_failure_or_uncertain"} or terminal.get("logical_sample_id") != metadata["logical_sample_id"] or terminal.get("failed_leaf_id") != metadata["failed_leaf_id"] or terminal.get("locked") != metadata["locked"]:
        raise ValueError("Repair terminal does not bind its logical sample and lock")
    response = terminal.get("response")
    if not isinstance(response, str) or terminal.get("response_sha256") != _sha(response) or terminal.get("response_provenance") not in {"provider_return", "provider_attempt_failure_content"}:
        raise ValueError("Repair terminal lacks raw response provenance")
    if status == "terminal_failure_or_uncertain":
        if not isinstance(terminal.get("error"), str) or terminal.get("error_sha256") != _sha(terminal["error"]):
            raise ValueError("Uncertain repair terminal lacks sealed error evidence")
        provider = terminal.get("provider_record")
        if provider is None:
            if terminal.get("provider_record_sha256") is not None or terminal.get("session_id_sha256") is not None or terminal.get("provider_attestation") != "unavailable":
                raise ValueError("Uncertain repair terminal lacks explicit unavailable attestation")
        elif terminal.get("provider_attestation") == "attested":
            _provider_attestation(terminal)
        elif terminal.get("provider_attestation") == "unavailable" and terminal.get("provider_record_sha256") == _sha(_canonical(provider)) and terminal.get("session_id_sha256") is None:
            pass
        else:
            raise ValueError("Uncertain repair terminal provider attestation is malformed")
    else:
        if terminal.get("provider_attestation") != "attested":
            raise ValueError("Repair terminal provider attestation is malformed")
        _provider_attestation(terminal)
        payload = parent._runner()._parse_model_json(response)
        kind = _quote_payload_kind(payload, metadata)
        normalized = terminal.get("normalized_verdicts")
        if not isinstance(normalized, list) or terminal.get("normalized_verdicts_sha256") != _sha(_canonical(normalized)):
            raise ValueError("Repair terminal normalized verdict evidence drifted")
        if status == "valid_quote_repair":
            if kind != "valid":
                raise ValueError("Accepted repair no longer has a literal valid quote")
            expected_normalized = parent._runner()._normalize_batch(payload, expected_ids=[leaf], artifact_id=str(metadata["item"]["item_id"]), bundle_id="prose.short_story", judge_id=f"{PROVIDER}:{MODEL}", run_id=attempt_id, artifact_text=Path(str(metadata["item"]["artifact"]["path"])).read_text(encoding="utf-8-sig"), context_texts=[Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in metadata["item"]["contexts"]])
            if normalized != expected_normalized:
                raise ValueError("Accepted repair normalization does not match its raw response")
        elif status == "invalid_quote_repair":
            if kind != "invalid_quote" or normalized:
                raise ValueError("Invalid-quote repair terminal does not match its raw response")
        elif kind == "non_quote":
            if normalized:
                raise ValueError("Non-quote repair terminal has unexpected normalized verdicts")
        else:
            if not isinstance(terminal.get("error"), str) or terminal.get("error_sha256") != _sha(terminal["error"]):
                raise ValueError("Non-quote repair terminal lacks its canonicalization error")
            try:
                parent._runner()._normalize_batch(payload, expected_ids=[leaf], artifact_id=str(metadata["item"]["item_id"]), bundle_id="prose.short_story", judge_id=f"{PROVIDER}:{MODEL}", run_id=attempt_id, artifact_text=Path(str(metadata["item"]["artifact"]["path"])).read_text(encoding="utf-8-sig"), context_texts=[Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in metadata["item"]["contexts"]])
            except Exception as error:
                if str(error) != terminal["error"]:
                    raise ValueError("Non-quote repair error does not match canonicalization") from error
            else:
                raise ValueError("Non-quote repair terminal rejected a canonically valid raw response")
    disclosures = [row for row in _rows(root / PUBLIC_DISCLOSURES) if row.get("repair_attempt_id") == attempt_id]
    if disclosures != [_disclosure(attempt_id, metadata, prompt)]:
        raise ValueError("Repair disclosure evidence is missing, duplicated, or drifted")
    journal = [row for row in _rows(root / PUBLIC_JOURNAL) if row.get("repair_attempt_id") == attempt_id]
    intent_public = {"event": "repair-attempt-intent", "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": leaf, "locked": metadata["locked"], "claim_sha256": claim_sha256, "prompt_sha256": _sha(prompt)}
    terminal_public = {"event": status, "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": leaf, "private_terminal_sha256": _sha(path.read_bytes())}
    combined = path.parent / "combined-validation.json"
    combined_value = _json(combined)
    if combined_value.get("format_version") != 1 or combined_value.get("repair_attempt_id") != attempt_id or not isinstance(combined_value.get("combined_state"), dict):
        raise ValueError("Repair combined-validation evidence drifted")
    terminal_public["combined_validation_sha256"] = _sha(combined.read_bytes())
    if journal != [intent_public, terminal_public]:
        raise ValueError("Repair public journal evidence is missing, duplicated, or drifted")
    return terminal


def _prior_repairs(parent: Any, original_private: Path, continuation_private: Path, root: Path, private: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    first = _json(continuation_private / "cell-17-repair" / "quote-only" / "terminal.json")
    all_terminals = [first] + [_verify_attempt(parent, original_private, root, path) for path in _terminal_paths(private)]
    replacements: dict[str, dict[str, Any]] = {}
    for index, terminal in enumerate(all_terminals):
        status = terminal.get("status")
        if index == 0 and status != "valid_quote_repair":
            raise ValueError("First quote repair drifted")
        if status == "valid_quote_repair":
            leaf = terminal.get("failed_leaf_id")
            row = _repair_response(terminal)
            if not isinstance(leaf, str) or row.get("question_id") != leaf or leaf in replacements:
                raise ValueError("Repair chain duplicates or misbinds a valid leaf")
            replacements[leaf] = row
    return replacements, all_terminals


def _combined_payload(original_rows: list[dict[str, Any]], replacements: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    seen = {str(row["question_id"]) for row in original_rows}
    if not set(replacements).issubset(seen):
        raise ValueError("Repair targets are absent from original cell 17")
    return {"verdicts": [dict(replacements.get(str(row["question_id"]), row)) for row in original_rows]}


def _combined_status(parent: Any, original_private: Path, continuation_private: Path, root: Path, private: Path) -> dict[str, Any]:
    cell, item, original_rows = _original_cell(parent, original_private)
    replacements, terminals = _prior_repairs(parent, original_private, continuation_private, root, private)
    for terminal in terminals[1:]:
        if terminal.get("status") in {"terminal_failure_or_uncertain", "non_quote_repair_failure"}:
            return {"status": "unavailable", "reason": terminal["status"], "attempts": len(terminals) - 1, "repaired_leaf_ids": sorted(replacements)}
    payload = _combined_payload(original_rows, replacements)
    try:
        normalized = parent._reparse_verdicts(_canonical(payload).decode("utf-8"), item, cell)
        return {"status": "valid", "attempts": len(terminals) - 1, "repaired_leaf_ids": sorted(replacements), "normalized_verdicts": normalized}
    except Exception as error:
        match = QUOTE_FAILURE.search(str(error))
        if not match:
            return {"status": "unavailable", "reason": "non_quote_combined_failure", "error": str(error), "attempts": len(terminals) - 1, "repaired_leaf_ids": sorted(replacements)}
        leaf = match.group(1)
        if leaf in replacements:
            raise ValueError("Canonical validation re-failed an accepted repair leaf")
        if len(terminals) - 1 >= MAX_ADDITIONAL_ATTEMPTS:
            return {"status": "unavailable", "reason": "quote_repair_cap_exhausted", "attempts": len(terminals) - 1, "repaired_leaf_ids": sorted(replacements), "failed_leaf_id": leaf}
        return {"status": "pending", "attempts": len(terminals) - 1, "repaired_leaf_ids": sorted(replacements), "failed_leaf_id": leaf, "combined_error": str(error)}


def _source_text(item: Mapping[str, Any]) -> str:
    artifact = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig")
    contexts = [Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]]
    return artifact + "\n" + "\n".join(contexts)


def _repair_prompt(parent: Any, original_private: Path, leaf: str) -> tuple[str, dict[str, Any]]:
    cell, item, rows = _original_cell(parent, original_private)
    source = next((row for row in rows if row["question_id"] == leaf), None)
    if source is None or source.get("verdict") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or isinstance(source.get("confidence"), bool) or not isinstance(source.get("confidence"), (int, float)) or not 0 <= source["confidence"] <= 1:
        raise ValueError("Original failed leaf lacks a lockable verdict and confidence")
    questions, _ = parent._compiled_questions(item)
    question = next((entry for entry in questions if str(entry["question"]["id"]) == leaf), None)
    if question is None:
        raise ValueError("Canonical failed leaf is absent from the compiled sequence")
    locked = {"question_id": leaf, "verdict": source["verdict"], "confidence": source["confidence"]}
    artifact = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig")
    contexts = [Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]]
    prompt = "\n\n".join((
        "Return one complete canonical HBQ verdict for this one question only. Do not change the locked verdict or confidence. Use a nonempty exact quote that occurs verbatim in the supplied artifact or context.",
        "LOCKED ORIGINAL: " + json.dumps(locked, ensure_ascii=False, sort_keys=True),
        "QUESTION: " + json.dumps(question["question"], ensure_ascii=False, sort_keys=True),
        "ARTIFACT:\n" + artifact,
        "CONTEXT:\n" + "\n\n".join(contexts),
    ))
    return prompt, {"cell": cell, "item": item, "locked": locked, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": leaf}


def _valid_quote(value: str, source: str) -> bool:
    return bool(value.strip()) and value in source


def _quote_payload_kind(payload: object, metadata: Mapping[str, Any]) -> str:
    rows = payload.get("verdicts") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return "non_quote"
    row = rows[0]
    if {key: row.get(key) for key in ("question_id", "verdict", "confidence")} != metadata["locked"]:
        return "non_quote"
    evidence = row.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return "non_quote"
    if not all(isinstance(entry, dict) and entry.get("kind") == "exact_quote" and isinstance(entry.get("exact_quote"), str) for entry in evidence):
        return "non_quote"
    return "valid" if all(_valid_quote(entry["exact_quote"], _source_text(metadata["item"])) for entry in evidence) else "invalid_quote"


def _known_sessions(original_work: Path, continuation_work: Path, continuation_private: Path, private: Path) -> set[str]:
    values: list[str] = []
    for journal in (original_work / "execution-journal.jsonl", continuation_work / "continuation-journal.jsonl"):
        for row in _rows(journal):
            session = row.get("session_id_sha256")
            if isinstance(session, str) and len(session) == 64:
                values.append(session)
    attempt_root = private / PRIVATE_ATTEMPTS
    attempt_terminals = sorted(attempt_root.glob("*/terminal.json")) if attempt_root.is_dir() else []
    for path in [continuation_private / "cell-17-repair" / "quote-only" / "terminal.json", *attempt_terminals]:
        terminal = _json(path)
        session = terminal.get("session_id_sha256")
        if isinstance(session, str) and len(session) == 64:
            values.append(session)
    if len(values) != len(set(values)):
        raise ValueError("Provider session identity was reused in repair evidence")
    return set(values)


def render_next_disclosure(work: Path, private_root: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path) -> dict[str, Any]:
    parent, _ = _verify(work, private_root, original_work, original_private, continuation_work, continuation_private)
    state = _combined_status(parent, original_private.resolve(), continuation_private.resolve(), work.resolve(), private_root.resolve())
    if state["status"] != "pending":
        return {"provider_calls": 0, "status": state["status"], "repair_state": state}
    prompt, metadata = _repair_prompt(parent, original_private.resolve(), str(state["failed_leaf_id"]))
    disclosure = _disclosure(f"cell17-quote-repair-chain-v2-{state['attempts'] + 1:02d}", metadata, prompt)
    return {"provider_calls": 0, "status": "pending", "disclosure": disclosure, "exact_rendered_prompt": prompt}


def _exception_provider_record(error: BaseException) -> Mapping[str, Any] | None:
    value = getattr(error, "provider_record", None)
    return value if isinstance(value, Mapping) else None


def _exception_content(error: BaseException) -> str | None:
    value = getattr(error, "content", None)
    return value if isinstance(value, str) else None


def _claim(root: Path) -> Path:
    path = root / CLAIM
    value = {"format_version": 1, "pid": os.getpid(), "claimed_at": datetime.now(UTC).isoformat(), "executor_sha256": _sha((HERE / "executor.py").read_bytes()), "journal_sha256": _sha((root / PUBLIC_JOURNAL).read_bytes()) if (root / PUBLIC_JOURNAL).is_file() else _sha(b"")}
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError("Exclusive repair claim exists; stop without duplicate dispatch") from error
    try:
        payload = _canonical(value) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            raise OSError("Partial repair claim write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def execute_one(work: Path, private_root: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, *, allow_remote: bool = False, timeout: float = 3600.0) -> dict[str, Any]:
    parent, _ = _verify(work, private_root, original_work, original_private, continuation_work, continuation_private)
    if not allow_remote:
        raise ValueError("Repair-chain execution sends disclosed writing; pass --allow-remote after review")
    root, private = work.resolve(), private_root.resolve()
    claim = _claim(root)
    destination: Path | None = None
    sealed = False
    try:
        parent, _ = _verify(root, private, original_work, original_private, continuation_work, continuation_private)
        state = _combined_status(parent, original_private.resolve(), continuation_private.resolve(), root, private)
        if state["status"] != "pending":
            return {"provider_calls": 0, "status": state["status"], "repair_state": state}
        prompt, metadata = _repair_prompt(parent, original_private.resolve(), str(state["failed_leaf_id"]))
        prior_replacements, _ = _prior_repairs(parent, original_private.resolve(), continuation_private.resolve(), root, private)
        attempt = int(state["attempts"]) + 1
        attempt_id = f"cell17-quote-repair-chain-v2-{attempt:02d}"
        destination = private / PRIVATE_ATTEMPTS / f"{attempt:02d}"
        if destination.exists():
            raise ValueError("Repair-chain attempt destination already exists and is immutable")
        claim_bytes = claim.read_bytes()
        claim_sha256 = _sha(claim_bytes)
        disclosure = _disclosure(attempt_id, metadata, prompt)
        _append(root / PUBLIC_DISCLOSURES, disclosure)
        _append(root / PUBLIC_JOURNAL, {"event": "repair-attempt-intent", "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "locked": metadata["locked"], "claim_sha256": claim_sha256, "prompt_sha256": _sha(prompt)})
        (destination / "claim.json").parent.mkdir(parents=True, exist_ok=True)
        (destination / "claim.json").write_bytes(claim_bytes)
        _atomic(destination / "attempt-intent.json", _attempt_intent(attempt_id, metadata, prompt, parent, claim_sha256))
        _atomic(destination / "dispatch-start.json", {"format_version": 1, "repair_attempt_id": attempt_id, "claim_sha256": claim_sha256, "prompt_sha256": _sha(prompt), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}})
        response: str | None = None
        provider_record: Mapping[str, Any] | None = None
        try:
            response, provider_record = parent._runner()._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=destination, response_schema=parent.SCHEMA_PATH, batch_number=1, timeout=timeout, attempt_number=1)
            reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None
            session = reported.get("session_id") if isinstance(reported, Mapping) else None
            if not isinstance(session, str) or not session or _sha(session) in _known_sessions(original_work.resolve(), continuation_work.resolve(), continuation_private.resolve(), private):
                raise ValueError("Repair session was missing or reused")
            payload = parent._runner()._parse_model_json(response)
            kind = _quote_payload_kind(payload, metadata); parse_error: str | None = None
            if kind == "valid":
                try:
                    normalized = parent._runner()._normalize_batch(payload, expected_ids=[metadata["failed_leaf_id"]], artifact_id=str(metadata["item"]["item_id"]), bundle_id="prose.short_story", judge_id=f"{PROVIDER}:{MODEL}", run_id=attempt_id, artifact_text=Path(str(metadata["item"]["artifact"]["path"])).read_text(encoding="utf-8-sig"), context_texts=[Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in metadata["item"]["contexts"]])
                    status = "valid_quote_repair"
                except Exception as error:
                    normalized, status, parse_error = [], "non_quote_repair_failure", str(error)
            else:
                normalized, status = [], "invalid_quote_repair" if kind == "invalid_quote" else "non_quote_repair_failure"
            terminal = {"format_version": 1, "status": status, "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "locked": metadata["locked"], "response": response, "response_sha256": _sha(response), "response_provenance": "provider_return", "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)), "provider_attestation": "attested", "session_id_sha256": _sha(session), "normalized_verdicts": normalized, "normalized_verdicts_sha256": _sha(_canonical(normalized))}
            if parse_error is not None:
                terminal.update({"error": parse_error, "error_sha256": _sha(parse_error)})
        except Exception as error:
            if provider_record is None:
                provider_record = _exception_provider_record(error)
            if response is None:
                response = _exception_content(error) or ""
            reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None
            session = reported.get("session_id") if isinstance(reported, Mapping) else None
            attested = isinstance(reported, Mapping) and reported.get("provider") == "openai" and reported.get("model") == MODEL and reported.get("reasoning_effort") == REASONING and isinstance(session, str) and bool(session)
            terminal = {"format_version": 1, "status": "terminal_failure_or_uncertain", "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "locked": metadata["locked"], "error": str(error), "error_sha256": _sha(str(error)), "response": response, "response_sha256": _sha(response), "response_provenance": "provider_attempt_failure_content" if _exception_content(error) is not None else "provider_return", "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)) if provider_record is not None else None, "provider_attestation": "attested" if attested else "unavailable", "session_id_sha256": _sha(session) if attested else None}
        _atomic(destination / "terminal.json", terminal)
        cell, item, original_rows = _original_cell(parent, original_private.resolve())
        replacements = dict(prior_replacements)
        if terminal["status"] == "valid_quote_repair":
            replacements[metadata["failed_leaf_id"]] = _repair_response(terminal)
        try:
            normalized_all = parent._reparse_verdicts(_canonical(_combined_payload(original_rows, replacements)).decode("utf-8"), item, cell)
            combined = {"status": "valid", "normalized_verdicts": normalized_all}
        except Exception as error:
            match = QUOTE_FAILURE.search(str(error))
            combined = {"status": "pending" if match and terminal["status"] in {"valid_quote_repair", "invalid_quote_repair"} else "unavailable", "failed_leaf_id": match.group(1) if match else None, "error": str(error)}
        _atomic(destination / "combined-validation.json", {"format_version": 1, "repair_attempt_id": attempt_id, "combined_state": combined})
        _append(root / PUBLIC_JOURNAL, {"event": terminal["status"], "repair_attempt_id": attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "private_terminal_sha256": _sha((destination / "terminal.json").read_bytes()), "combined_validation_sha256": _sha((destination / "combined-validation.json").read_bytes())})
        sealed = True
        return {"provider_calls": 1, "status": terminal["status"], "repair_attempt_id": attempt_id, "combined_status": combined["status"]}
    finally:
        if sealed or destination is None:
            claim.unlink(missing_ok=True)


def _sealed_primary(continuation_work: Path) -> dict[str, Any]:
    settlement = _json(continuation_work / "offline-settlement.json")
    primary = settlement.get("primary_analysis")
    if settlement.get("study_id") != "hbq-ai-writer-preface-v1-continuation-v1" or not isinstance(primary, dict):
        raise ValueError("Sealed continuation primary analysis is malformed")
    valid, expected, missing, no_imputation = primary.get("original_valid_cells"), primary.get("original_expected_cells"), primary.get("missing_original_cell"), primary.get("no_imputation")
    if isinstance(valid, bool) or not isinstance(valid, int) or isinstance(expected, bool) or not isinstance(expected, int) or missing != 17 or no_imputation is not True or not 0 <= valid <= expected:
        raise ValueError("Sealed continuation primary counts are malformed")
    return {"original_valid_cells": valid, "original_expected_cells": expected, "missing_original_cell": missing, "no_imputation": no_imputation, "sealed_continuation_primary_sha256": _sha(_canonical(primary))}


def settle_offline(work: Path, private_root: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path) -> dict[str, Any]:
    parent, binding = _verify(work, private_root, original_work, original_private, continuation_work, continuation_private)
    state = _combined_status(parent, original_private.resolve(), continuation_private.resolve(), work.resolve(), private_root.resolve())
    summary = {"format_version": 1, "study_id": contract()["study_id"], "provider_calls": 0, "binding_sha256": _sha(_canonical(binding)), "primary_analysis": _sealed_primary(continuation_work.resolve()), "repair_sensitivity": {"logical_sample_id": "preface-cell-0017", "separate_from_primary": True, "status": state["status"], "reason": state.get("reason"), "additional_attempts": state["attempts"], "accepted_repaired_leaf_ids": state["repaired_leaf_ids"], "complete_combined_cell_validates": state["status"] == "valid"}, "automatic_wording_decision": False}
    path = work.resolve() / PUBLIC_SETTLEMENT
    if path.exists() and _json(path) != summary and _json(path).get("repair_sensitivity", {}).get("status") != "pending":
        raise ValueError("Offline settlement is immutable after final repair state")
    _atomic(path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "private_root", "original_work", "original_private", "continuation_work", "continuation_private"):
        parser.add_argument(name, type=Path)
    for name in ("prepare", "render_next_disclosure", "execute_one", "settle_offline"):
        parser.add_argument("--" + name.replace("_", "-"), action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args()
    actions = [name for name in ("prepare", "render_next_disclosure", "execute_one", "settle_offline") if getattr(args, name)]
    if len(actions) != 1:
        parser.error("choose exactly one action")
    common = (args.work, args.private_root, args.original_work, args.original_private, args.continuation_work, args.continuation_private)
    if args.prepare:
        result = prepare(*common)
    elif args.render_next_disclosure:
        result = render_next_disclosure(*common)
    elif args.execute_one:
        result = execute_one(*common, allow_remote=args.allow_remote, timeout=args.timeout)
    else:
        result = settle_offline(*common)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
