"""Sealed suffix executor and cell-17 repair sensitivity path for preface pilot v1."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
PARENT_PACKAGE = HERE.parent / "hbq-ai-writer-preface-v1-pilot-executor-v1"
CONTRACT_PATH = HERE / "study-contract.json"
PUBLIC_BINDING = "continuation-binding.json"
PUBLIC_SCHEDULE = "suffix-schedule.jsonl"
PUBLIC_JOURNAL = "continuation-journal.jsonl"
PUBLIC_DISCLOSURES = "outbound-disclosures.jsonl"
PUBLIC_SETTLEMENT = "offline-settlement.json"
PRIVATE_CELLS = "suffix-cells"
PRIVATE_CAPACITY = "capacity"
PRIVATE_REPAIRS = "cell-17-repair"
MODEL, REASONING, PROVIDER = "gpt-5.6-sol", "high", "codex"
SUFFIX = tuple(range(18, 25))
CAPACITY_MAX_AGE = timedelta(minutes=10)


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


def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical(value) + b"\n")
    os.replace(temporary, path)


def _append(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as output:
        output.write(_canonical(value) + b"\n")


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Malformed JSONL: {path.name}")
        rows.append(value)
    return rows


def _fingerprint(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": _sha(data)}


def _disjoint(*roots: Path) -> bool:
    resolved = [path.resolve() for path in roots]
    return all(left != right and not _inside(left, right) and not _inside(right, left) for index, left in enumerate(resolved) for right in resolved[index + 1:])


def _inside(root: Path, child: Path) -> bool:
    try:
        child.relative_to(root)
    except ValueError:
        return False
    return True


def _parent() -> Any:
    name = "hbq_ai_writer_preface_parent_executor_v1"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, PARENT_PACKAGE / "executor.py")
    if spec is None or spec.loader is None:
        raise ValueError("Parent executor cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    value = _json(CONTRACT_PATH)
    parent = value.get("parent")
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-ai-writer-preface-v1-continuation-v1" or not isinstance(parent, dict):
        raise ValueError("Continuation contract drifted")
    for key in ("executor_sha256", "contract_sha256", "executor_binding_sha256", "schedule_sha256", "journal_through_cell_17_sha256", "cell_17_terminal_sha256", "cell_17_raw_response_sha256"):
        if not isinstance(parent.get(key), str) or len(parent[key]) != 64:
            raise ValueError("Continuation parent binding is malformed")
    if _sha((PARENT_PACKAGE / "executor.py").read_bytes()) != parent["executor_sha256"] or _sha((PARENT_PACKAGE / "study-contract.json").read_bytes()) != parent["contract_sha256"]:
        raise ValueError("Frozen parent executor or contract drifted")
    return value


def _original(original_work: Path, original_private: Path) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    fixed = contract()["parent"]
    work, private = original_work.resolve(), original_private.resolve()
    if not _disjoint(work, private):
        raise ValueError("Original public/private evidence roots must be disjoint")
    schedule_path, journal_path = work / "pilot-schedule.jsonl", work / "execution-journal.jsonl"
    if _sha((work / "executor-binding.json").read_bytes()) != fixed["executor_binding_sha256"] or _sha(schedule_path.read_bytes()) != fixed["schedule_sha256"] or _sha(journal_path.read_bytes()) != fixed["journal_through_cell_17_sha256"]:
        raise ValueError("Original schedule or journal prefix drifted")
    schedule = _rows(schedule_path)
    if [row.get("sequence") for row in schedule] != list(range(1, 25)):
        raise ValueError("Original schedule geometry drifted")
    terminal17 = private / "cells" / "0017" / "terminal.json"
    if _sha(terminal17.read_bytes()) != fixed["cell_17_terminal_sha256"] or _json(terminal17).get("status") != "terminal_failure_or_uncertain":
        raise ValueError("Original cell 17 terminal failure drifted")
    raw17 = private / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json"
    if _sha(raw17.read_bytes()) != fixed["cell_17_raw_response_sha256"]:
        raise ValueError("Original cell 17 raw response drifted")
    journal = _rows(journal_path)
    if len(journal) != 34 or journal[-1].get("event") != "terminal_failure_or_uncertain" or journal[-1].get("sequence") != 17:
        raise ValueError("Original journal does not end in sealed cell 17 failure")
    cell_hashes: dict[str, str] = {"0017": _sha(terminal17.read_bytes())}
    for sequence in range(1, 17):
        terminal = private / "cells" / f"{sequence:04d}" / "terminal.json"
        value = _json(terminal)
        if value.get("status") != "completed":
            raise ValueError("Original valid-cell evidence drifted")
        cell_hashes[f"{sequence:04d}"] = _sha(terminal.read_bytes())
    return _parent(), schedule, cell_hashes


def _binding(original_work: Path, original_private: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    parent, schedule, cells = _original(original_work, original_private)
    suffix = [dict(row) for row in schedule if int(row["sequence"]) in SUFFIX]
    if [row["sequence"] for row in suffix] != list(SUFFIX):
        raise ValueError("Continuation suffix geometry drifted")
    binding = {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "contract": _fingerprint(CONTRACT_PATH),
        "executor": _fingerprint(HERE / "executor.py"),
        "parent_executor": _fingerprint(PARENT_PACKAGE / "executor.py"),
        "original": {
            "public_binding": _fingerprint(original_work.resolve() / "executor-binding.json"),
            "schedule": _fingerprint(original_work.resolve() / "pilot-schedule.jsonl"),
            "journal_through_cell_17": _fingerprint(original_work.resolve() / "execution-journal.jsonl"),
            "cells_1_17": cells,
            "cell_17_raw_response": _fingerprint(original_private.resolve() / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json"),
        },
        "suffix_schedule_sha256": _sha(_canonical(suffix)),
        "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING},
        "parent_runtime": {"binary_prompt": _fingerprint(parent.BINARY_PROMPT_PATH), "response_schema": _fingerprint(parent.SCHEMA_PATH), "runner": _fingerprint(parent.REPOSITORY / "src" / "hbqrs" / "runner.py")},
        "original_roots": "read-only evidence; no continuation function writes them",
    }
    return binding, suffix


def prepare(work: Path, private_root: Path, original_work: Path, original_private: Path) -> dict[str, Any]:
    root, private = work.resolve(), private_root.resolve()
    if not _disjoint(root, private, original_work.resolve(), original_private.resolve()):
        raise ValueError("Continuation and original evidence roots must be pairwise disjoint")
    if (root.exists() and any(root.iterdir())) or (private.exists() and any(private.iterdir())):
        raise ValueError("Prepare requires fresh, empty continuation roots")
    binding, suffix = _binding(original_work, original_private)
    root.mkdir(parents=True, exist_ok=True); private.mkdir(parents=True, exist_ok=True)
    _atomic(root / PUBLIC_BINDING, binding)
    (root / PUBLIC_SCHEDULE).write_bytes(b"".join(_canonical(row) + b"\n" for row in suffix))
    return {"provider_calls": 0, "suffix_cells": len(suffix), "scored_cells_remaining": len(suffix), "repair_pending": True}


def _verify(work: Path, private_root: Path, original_work: Path, original_private: Path) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    root, private = work.resolve(), private_root.resolve()
    if not _disjoint(root, private, original_work.resolve(), original_private.resolve()):
        raise ValueError("Continuation and original evidence roots must remain disjoint")
    expected, suffix = _binding(original_work, original_private)
    if _json(root / PUBLIC_BINDING) != expected or _rows(root / PUBLIC_SCHEDULE) != suffix:
        raise ValueError("Prepared continuation binding or suffix schedule drifted")
    return _parent(), suffix, expected


def _terminal(private: Path, sequence: int) -> Path:
    return private / PRIVATE_CELLS / f"{sequence:04d}" / "terminal.json"


def _settled(work: Path, private: Path, suffix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    records = _rows(work / PUBLIC_JOURNAL)
    for index, cell in enumerate(suffix):
        matching = [record for record in records if record.get("sequence") == cell["sequence"] and record.get("event") in {"completed", "terminal_failure_or_uncertain"}]
        if len(matching) > 1:
            raise ValueError("Continuation cell has multiple terminal records")
        terminal = _terminal(private, int(cell["sequence"]))
        if matching:
            if index != len(result):
                raise ValueError("Continuation has a terminal after an earlier schedule gap")
            if not terminal.is_file():
                raise ValueError("Continuation terminal record lacks private terminal")
            value = _json(terminal)
            if value.get("cell") != cell or value.get("status") not in {"completed", "terminal_failure_or_uncertain"} or _sha(terminal.read_bytes()) != matching[0].get("private_terminal_sha256"):
                raise ValueError("Continuation terminal evidence drifted")
            result.append(cell)
        elif terminal.exists():
            raise ValueError("Unjournaled continuation terminal is ambiguous")
    return result


def _known_sessions(work: Path, private: Path, original_work: Path) -> set[str]:
    listed = [str(row["session_id_sha256"]) for row in _rows(original_work / "execution-journal.jsonl") if row.get("event") == "completed"]
    for path in work.glob("capacity-preflight-*.json"):
        listed.append(str(_json(path)["session_id_sha256"]))
    for terminal in list((private / PRIVATE_CELLS).glob("*/terminal.json")) + list((private / PRIVATE_REPAIRS).glob("*/terminal.json")):
        value = _json(terminal)
        session = value.get("session_id_sha256")
        if isinstance(session, str) and len(session) == 64: listed.append(session)
    values = set(listed)
    if len(values) != len(listed): raise ValueError("Provider session identity was reused in continuation evidence")
    return values


def _next(work: Path, private: Path, suffix: list[dict[str, Any]]) -> dict[str, Any] | None:
    done = _settled(work, private, suffix)
    return suffix[len(done)] if len(done) < len(suffix) else None


def _capacity_path(work: Path, sequence: int) -> Path:
    return work / f"capacity-preflight-{sequence:04d}.json"


def _capacity_prompt() -> str:
    return 'Return exactly this JSON object and nothing else: {"ready": true}. This is an unscored capacity preflight; do not evaluate any writing.'


def _capacity(work: Path, private: Path, sequence: int, *, now: datetime | None = None) -> dict[str, Any]:
    receipt = _json(_capacity_path(work, sequence))
    if receipt.get("sequence") != sequence or receipt.get("status") != "ready" or receipt.get("provider") != {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}:
        raise ValueError("Capacity preflight evidence drifted")
    observed = datetime.fromisoformat(str(receipt.get("observed_at")))
    current = now or datetime.now(UTC)
    if observed.tzinfo is None or observed > current + timedelta(seconds=30) or current - observed > CAPACITY_MAX_AGE:
        raise ValueError("Capacity preflight is not fresh enough for a scored send")
    terminal = private / PRIVATE_CAPACITY / f"{sequence:04d}" / "terminal.json"
    if _sha(terminal.read_bytes()) != receipt.get("private_terminal_sha256") or _json(terminal).get("status") != "ready":
        raise ValueError("Capacity receipt does not bind private evidence")
    return receipt


def run_capacity_preflight(work: Path, private_root: Path, original_work: Path, original_private: Path, *, allow_remote: bool = False, timeout: float = 120.0) -> dict[str, Any]:
    parent, suffix, _ = _verify(work, private_root, original_work, original_private)
    root, private = work.resolve(), private_root.resolve()
    if not allow_remote:
        raise ValueError("Capacity preflight uses Codex; pass --allow-remote after review")
    cell = _next(root, private, suffix)
    if cell is None: return {"provider_calls": 0, "status": "complete"}
    sequence = int(cell["sequence"]); path = _capacity_path(root, sequence)
    if path.exists():
        _capacity(root, private, sequence); raise ValueError("Fresh capacity receipt already exists")
    prompt = _capacity_prompt(); destination = private / PRIVATE_CAPACITY / f"{sequence:04d}"
    disclosure = {"event": "unscored_capacity_preflight_disclosure", "sequence": sequence, "destination": "Codex CLI -> authenticated OpenAI service", "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "outbound_content": "Only the fixed no-writing capacity prompt", "prompt_sha256": _sha(prompt)}
    _append(root / PUBLIC_DISCLOSURES, disclosure)
    _atomic(destination / "attempt-intent.json", {"format_version": 1, "sequence": sequence, "kind": "unscored_capacity_preflight", "prompt": prompt, "prompt_sha256": _sha(prompt)})
    schema = destination / "capacity-response.schema.json"; _atomic(schema, {"type": "object", "additionalProperties": False, "required": ["ready"], "properties": {"ready": {"type": "boolean"}}})
    try:
        _atomic(destination / "dispatch-start.json", {"format_version": 1, "sequence": sequence, "prompt_sha256": _sha(prompt)})
        response, provider_record = parent._runner()._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=destination, response_schema=schema, batch_number=1, timeout=timeout, attempt_number=1)
        if json.loads(response) != {"ready": True}: raise ValueError("Capacity preflight response did not attest ready")
        reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None; session = reported.get("session_id") if isinstance(reported, Mapping) else None
        if not isinstance(session, str) or not session or _sha(session) in _known_sessions(root, private, original_work.resolve()): raise ValueError("Capacity preflight session was missing or reused")
        terminal = {"format_version": 1, "status": "ready", "prompt_sha256": _sha(prompt), "response": response, "response_sha256": _sha(response), "provider_record": provider_record}
        _atomic(destination / "terminal.json", terminal)
        receipt = {"format_version": 1, "study_id": contract()["study_id"], "sequence": sequence, "status": "ready", "observed_at": datetime.now(UTC).isoformat(), "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "prompt_sha256": _sha(prompt), "response_sha256": _sha(response), "provider_record_sha256": _sha(_canonical(provider_record)), "session_id_sha256": _sha(session), "private_terminal_sha256": _sha((destination / "terminal.json").read_bytes())}
        _atomic(path, receipt); return {"provider_calls": 1, "scored_provider_calls": 0, "sequence": sequence, "status": "ready"}
    except Exception as error:
        _atomic(destination / "terminal.json", {"format_version": 1, "status": "failed", "error": str(error), "error_sha256": _sha(str(error)), "prompt_sha256": _sha(prompt)})
        raise ValueError("Capacity preflight failed; do not score this cell") from error


def _disclosure(parent: Any, original_private: Path, cell: Mapping[str, Any]) -> tuple[dict[str, Any], str, Any]:
    item = parent._item(original_private.resolve(), str(cell["item_id"])); prompt, ids, question_hash = parent._rendered_prompt(item, str(cell["arm"]))
    if _sha(prompt) != cell["prompt_sha256"] or len(prompt.encode("utf-8")) != cell["prompt_bytes"] or _sha(_canonical(ids)) != cell["question_ids_sha256"] or question_hash != cell["compiled_question_payload_sha256"]:
        raise ValueError("Original suffix prompt binding drifted")
    disclosure = {"event": "scored_outbound_disclosure", "sequence": cell["sequence"], "destination": "Codex CLI -> authenticated OpenAI service", "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "cell": cell, "outbound_artifacts": parent._safe_item(item), "outbound_content": "Exact frozen artifact, contexts, full HBQ sequence and treatment preface; actual provenance is not sent.", "paid_api": False, "human_judgment": False}
    return disclosure, prompt, item


def render_next_disclosure(work: Path, private_root: Path, original_work: Path, original_private: Path) -> dict[str, Any]:
    parent, suffix, _ = _verify(work, private_root, original_work, original_private); cell = _next(work.resolve(), private_root.resolve(), suffix)
    if cell is None: return {"provider_calls": 0, "status": "complete"}
    disclosure, prompt, _ = _disclosure(parent, original_private, cell)
    return {"provider_calls": 0, "disclosure": disclosure, "exact_rendered_prompt": prompt}


def execute_one(work: Path, private_root: Path, original_work: Path, original_private: Path, *, allow_remote: bool = False, timeout: float = 3600.0, now: datetime | None = None) -> dict[str, Any]:
    parent, suffix, _ = _verify(work, private_root, original_work, original_private)
    root, private = work.resolve(), private_root.resolve()
    if not allow_remote: raise ValueError("This executor sends disclosed writing to Codex; pass --allow-remote after review")
    cell = _next(root, private, suffix)
    if cell is None: return {"provider_calls": 0, "status": "complete"}
    sequence = int(cell["sequence"]); capacity = _capacity(root, private, sequence, now=now)
    disclosure, prompt, item = _disclosure(parent, original_private, cell); _append(root / PUBLIC_DISCLOSURES, disclosure); _append(root / PUBLIC_JOURNAL, {"event": "attempt-intent", **cell})
    destination = private / PRIVATE_CELLS / f"{sequence:04d}"
    _atomic(destination / "attempt-intent.json", {"format_version": 1, "cell": cell, "rendered_prompt": prompt, "rendered_prompt_sha256": _sha(prompt), "capacity_preflight_sha256": _sha(_canonical(capacity))})
    response: str | None = None; provider_record: Mapping[str, Any] | None = None
    try:
        _atomic(destination / "dispatch-start.json", {"format_version": 1, "sequence": sequence, "prompt_sha256": _sha(prompt)})
        response, provider_record = parent._runner()._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=destination, response_schema=parent.SCHEMA_PATH, batch_number=1, timeout=timeout, attempt_number=1)
        verdicts = parent._reparse_verdicts(response, item, cell); reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None; session = reported.get("session_id") if isinstance(reported, Mapping) else None
        if not isinstance(session, str) or not session or _sha(session) in _known_sessions(root, private, original_work.resolve()): raise ValueError("Scored session was missing or reused")
        terminal = {"format_version": 1, "status": "completed", "cell": cell, "response": response, "response_sha256": _sha(response), "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)), "session_id_sha256": _sha(session), "verdicts": verdicts, "verdicts_sha256": _sha(_canonical(verdicts))}
        _atomic(destination / "terminal.json", terminal); _append(root / PUBLIC_JOURNAL, {"event": "completed", "sequence": sequence, "prompt_sha256": cell["prompt_sha256"], "private_terminal_sha256": _sha((destination / "terminal.json").read_bytes()), "provider_record_sha256": terminal["provider_record_sha256"], "session_id_sha256": terminal["session_id_sha256"], "verdicts_sha256": terminal["verdicts_sha256"]})
        return {"provider_calls": 1, "scored_provider_calls": 1, "sequence": sequence, "status": "completed"}
    except Exception as error:
        if provider_record is None: provider_record = _exception_provider_record(error)
        terminal = {"format_version": 1, "status": "terminal_failure_or_uncertain", "cell": cell, "error": str(error), "error_sha256": _sha(str(error)), "response_sha256": _sha(response) if isinstance(response, str) else None, "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)) if provider_record is not None else None, "session_id_sha256": _sha(str(provider_record["reported"]["session_id"])) if isinstance(provider_record, Mapping) and isinstance(provider_record.get("reported"), Mapping) and isinstance(provider_record["reported"].get("session_id"), str) else None}
        _atomic(destination / "terminal.json", terminal); _append(root / PUBLIC_JOURNAL, {"event": "terminal_failure_or_uncertain", "sequence": sequence, "prompt_sha256": cell["prompt_sha256"], "private_terminal_sha256": _sha((destination / "terminal.json").read_bytes())})
        return {"provider_calls": 1, "scored_provider_calls": 1, "sequence": sequence, "status": "terminal_failure_or_uncertain"}


def _cell17_source(parent: Any, original_private: Path) -> tuple[dict[str, Any], dict[str, Any], str, str, Any]:
    terminal_root = original_private.resolve() / "cells" / "0017"
    terminal = _json(terminal_root / "terminal.json")
    cell = terminal.get("cell")
    if terminal.get("status") != "terminal_failure_or_uncertain" or not isinstance(cell, dict) or cell.get("sequence") != 17:
        raise ValueError("Original cell 17 is not the sealed repair target")
    error = terminal.get("error")
    if not isinstance(error, str) or "Evidence item" not in error or "exact_quote" not in error:
        raise ValueError("Original failure metadata does not identify a quote-only repair")
    leaf = error.split(" for ", 1)[1].split(" has an exact_quote", 1)[0]
    response_path = terminal_root / "responses" / "batch-0001.attempt-0001.message.json"
    try:
        payload = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Original cell 17 raw response is unavailable for a locked repair") from exc
    verdicts = payload.get("verdicts") if isinstance(payload, dict) else None
    source = next((row for row in verdicts if isinstance(row, dict) and row.get("question_id") == leaf), None) if isinstance(verdicts, list) else None
    confidence = source.get("confidence") if isinstance(source, dict) else None
    if source is None or source.get("verdict") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("Original failed leaf lacks a lockable verdict and confidence")
    item = parent._item(original_private.resolve(), str(cell["item_id"]))
    questions, _ = parent._compiled_questions(item)
    question = next((entry for entry in questions if str(entry["question"]["id"]) == leaf), None)
    if question is None:
        raise ValueError("Original failed leaf no longer exists in the compiled question sequence")
    return cell, source, leaf, str(error), (item, question)


def _repair_prompt(parent: Any, original_private: Path, *, full_regrade: bool) -> tuple[str, dict[str, Any]]:
    cell, source, leaf, _error, bundle = _cell17_source(parent, original_private)
    item, question = bundle
    artifact = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig")
    contexts = [Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]]
    locked = {"question_id": leaf, "verdict": source["verdict"], "confidence": source["confidence"]}
    if full_regrade:
        instruction = "Return one complete canonical HBQ verdict for this one question only. This is a fresh, separately labelled regrade, not a new vote."
        schema = parent.SCHEMA_PATH
        locked_for_prompt: dict[str, Any] | None = None
    else:
        instruction = "Return one complete canonical HBQ verdict for this one question only. Do not change the locked verdict or confidence. Use a nonempty exact quote that occurs verbatim in the supplied artifact or context."
        schema = parent.SCHEMA_PATH
        locked_for_prompt = locked
    parts = [instruction]
    if locked_for_prompt is not None: parts.append("LOCKED ORIGINAL: " + json.dumps(locked_for_prompt, ensure_ascii=False, sort_keys=True))
    parts.extend(["QUESTION: " + json.dumps(question["question"], ensure_ascii=False, sort_keys=True), "ARTIFACT:\n" + artifact, "CONTEXT:\n" + "\n\n".join(contexts)])
    prompt = "\n\n".join(parts)
    return prompt, {"cell": cell, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": leaf, "locked": locked, "response_schema": schema}


def _repair_text(parent: Any, original_private: Path) -> str:
    item = _cell17_source(parent, original_private)[4][0]
    return Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig") + "\n" + "\n".join(Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"])


def _normalize_single_leaf(parent: Any, original_private: Path, response: str, metadata: Mapping[str, Any], repair_attempt_id: str) -> list[dict[str, Any]]:
    cell, _source, leaf, _error, bundle = _cell17_source(parent, original_private)
    item, _question = bundle
    payload = parent._runner()._parse_model_json(response)
    artifact = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig")
    contexts = [Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]]
    return parent._runner()._normalize_batch(payload, expected_ids=[leaf], artifact_id=str(item["item_id"]), bundle_id="prose.short_story", judge_id=f"{PROVIDER}:{MODEL}", run_id=repair_attempt_id, artifact_text=artifact, context_texts=contexts)


def _valid_quote(value: str, source_text: str) -> bool:
    return bool(value.strip()) and value in source_text


def _exception_provider_record(error: BaseException) -> Mapping[str, Any] | None:
    value = getattr(error, "provider_record", None)
    return value if isinstance(value, Mapping) else None


def _quote_repair_payload_valid(payload: object, metadata: Mapping[str, Any], source_text: str) -> bool:
    rows = payload.get("verdicts") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict): return False
    row = rows[0]
    if {key: row.get(key) for key in ("question_id", "verdict", "confidence")} != metadata["locked"]: return False
    evidence = row.get("evidence")
    return isinstance(evidence, list) and bool(evidence) and all(isinstance(entry, dict) and entry.get("kind") == "exact_quote" and isinstance(entry.get("exact_quote"), str) and _valid_quote(entry["exact_quote"], source_text) for entry in evidence)


def render_repair_disclosure(work: Path, private_root: Path, original_work: Path, original_private: Path, *, full_regrade: bool = False) -> dict[str, Any]:
    parent, _suffix, _ = _verify(work, private_root, original_work, original_private)
    prompt, metadata = _repair_prompt(parent, original_private, full_regrade=full_regrade)
    outbound = "Only the failed leaf, artifact, and relevant context; this is a fresh regrade with no locked original verdict or confidence. Actual provenance is not sent." if full_regrade else "Only the failed leaf, locked original fields, artifact, and relevant context; actual provenance is not sent."
    return {"provider_calls": 0, "disclosure": {"event": "cell_17_repair_disclosure", "destination": "Codex CLI -> authenticated OpenAI service", "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "repair_kind": "full_single_leaf_regrade" if full_regrade else "quote_only", "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "outbound_content": outbound, "prompt_sha256": _sha(prompt)}, "exact_rendered_prompt": prompt}


def repair_cell17(work: Path, private_root: Path, original_work: Path, original_private: Path, *, allow_remote: bool = False, full_regrade: bool = False, timeout: float = 3600.0) -> dict[str, Any]:
    parent, _suffix, _ = _verify(work, private_root, original_work, original_private)
    root, private = work.resolve(), private_root.resolve()
    if not allow_remote: raise ValueError("Cell 17 repair sends disclosed writing; pass --allow-remote after review")
    repair_root = private / PRIVATE_REPAIRS
    quote_terminal = repair_root / "quote-only" / "terminal.json"
    full_terminal = repair_root / "full-single-leaf-regrade" / "terminal.json"
    if full_regrade:
        if not quote_terminal.is_file() or _json(quote_terminal).get("status") != "invalid_quote_repair":
            raise ValueError("Full regrade is allowed only after an invalid quote-only repair")
        destination, repair_attempt_id = full_terminal.parent, "cell17-full-regrade-v1"
    else:
        if quote_terminal.exists() or full_terminal.exists(): raise ValueError("Cell 17 repair attempts are bounded and already sealed")
        destination, repair_attempt_id = quote_terminal.parent, "cell17-quote-repair-v1"
    if destination.exists():
        raise ValueError("Cell 17 repair destination already exists and is immutable")
    prompt, metadata = _repair_prompt(parent, original_private, full_regrade=full_regrade)
    disclosure = render_repair_disclosure(root, private, original_work, original_private, full_regrade=full_regrade)["disclosure"]
    _append(root / PUBLIC_DISCLOSURES, disclosure); _append(root / PUBLIC_JOURNAL, {"event": "repair-attempt-intent", "repair_attempt_id": repair_attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"]})
    schema = metadata["response_schema"]; _atomic(destination / "attempt-intent.json", {"format_version": 1, "repair_attempt_id": repair_attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "locked": metadata["locked"], "prompt": prompt, "prompt_sha256": _sha(prompt), "response_schema": _fingerprint(schema)})
    response: str | None = None; provider_record: Mapping[str, Any] | None = None
    try:
        _atomic(destination / "dispatch-start.json", {"format_version": 1, "repair_attempt_id": repair_attempt_id, "prompt_sha256": _sha(prompt)})
        response, provider_record = parent._runner()._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=destination, response_schema=schema, batch_number=1, timeout=timeout, attempt_number=1)
        reported = provider_record.get("reported") if isinstance(provider_record, Mapping) else None; session = reported.get("session_id") if isinstance(reported, Mapping) else None
        if not isinstance(session, str) or not session or _sha(session) in _known_sessions(root, private, original_work.resolve()): raise ValueError("Repair session was missing or reused")
        payload = parent._runner()._parse_model_json(response)
        if full_regrade:
            normalized = _normalize_single_leaf(parent, original_private, response, metadata, repair_attempt_id)
            status = "valid_full_single_leaf_regrade"
        else:
            if _quote_repair_payload_valid(payload, metadata, _repair_text(parent, original_private)):
                try:
                    normalized = _normalize_single_leaf(parent, original_private, response, metadata, repair_attempt_id)
                    status = "valid_quote_repair"
                except Exception:
                    normalized = []
                    status = "invalid_quote_repair"
            else:
                normalized = []
                status = "invalid_quote_repair"
        terminal = {"format_version": 1, "status": status, "repair_attempt_id": repair_attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "locked": metadata["locked"], "response": response, "response_sha256": _sha(response), "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)), "session_id_sha256": _sha(session), "normalized_verdicts": normalized, "normalized_verdicts_sha256": _sha(_canonical(normalized))}
        _atomic(destination / "terminal.json", terminal); _append(root / PUBLIC_JOURNAL, {"event": status, "repair_attempt_id": repair_attempt_id, "logical_sample_id": metadata["logical_sample_id"], "failed_leaf_id": metadata["failed_leaf_id"], "private_terminal_sha256": _sha((destination / "terminal.json").read_bytes())})
        return {"provider_calls": 1, "status": status, "repair_attempt_id": repair_attempt_id}
    except Exception as error:
        if provider_record is None: provider_record = _exception_provider_record(error)
        _atomic(destination / "terminal.json", {"format_version": 1, "status": "terminal_failure_or_uncertain", "repair_attempt_id": repair_attempt_id, "logical_sample_id": metadata["logical_sample_id"], "error": str(error), "error_sha256": _sha(str(error)), "response_sha256": _sha(response) if isinstance(response, str) else None, "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)) if provider_record is not None else None, "session_id_sha256": _sha(str(provider_record["reported"]["session_id"])) if isinstance(provider_record, Mapping) and isinstance(provider_record.get("reported"), Mapping) and isinstance(provider_record["reported"].get("session_id"), str) else None})
        _append(root / PUBLIC_JOURNAL, {"event": "repair_terminal_failure_or_uncertain", "repair_attempt_id": repair_attempt_id, "logical_sample_id": metadata["logical_sample_id"], "private_terminal_sha256": _sha((destination / "terminal.json").read_bytes())})
        return {"provider_calls": 1, "status": "terminal_failure_or_uncertain", "repair_attempt_id": repair_attempt_id}


def settle_offline(work: Path, private_root: Path, original_work: Path, original_private: Path) -> dict[str, Any]:
    _parent, suffix, binding = _verify(work, private_root, original_work, original_private)
    root, private = work.resolve(), private_root.resolve(); settled = _settled(root, private, suffix)
    if len(settled) != len(suffix): raise ValueError("Offline settlement requires every suffix cell to be terminal")
    completed = [cell for cell in settled if _json(_terminal(private, int(cell["sequence"]))).get("status") == "completed"]
    failures = [cell for cell in settled if cell not in completed]
    original_schedule = _rows(original_work.resolve() / "pilot-schedule.jsonl")
    valid_sequences = set(range(1, 17)) | {int(cell["sequence"]) for cell in completed}
    arm_valid = {arm: sum(1 for row in original_schedule if row["arm"] == arm and int(row["sequence"]) in valid_sequences) for arm in ("none", "current_full", "strictness_only")}
    pair_counts: dict[tuple[str, str], int] = {}
    for row in original_schedule:
        key = (str(row["item_id"]), str(row["arm"]))
        pair_counts[key] = pair_counts.get(key, 0) + (1 if int(row["sequence"]) in valid_sequences else 0)
    intact_repeatability_units = sum(1 for count in pair_counts.values() if count == 2)
    arm_units = {arm: sum(1 for (item_id, unit_arm), count in pair_counts.items() if unit_arm == arm and count == 2) for arm in ("none", "current_full", "strictness_only")}
    unit_table = [{"item_id": item_id, "arm": arm, "observations": count, "included_in_primary": count == 2, "input_weight_if_included": (1 / arm_units[arm]) if count == 2 else 0.0} for (item_id, arm), count in sorted(pair_counts.items())]
    repair = private / PRIVATE_REPAIRS / "quote-only" / "terminal.json"
    full = private / PRIVATE_REPAIRS / "full-single-leaf-regrade" / "terminal.json"
    repair_status = _json(full).get("status") if full.exists() else (_json(repair).get("status") if repair.exists() else "not_attempted")
    summary = {"format_version": 1, "study_id": contract()["study_id"], "provider_calls": 0, "binding_sha256": _sha(_canonical(binding)), "primary_analysis": {"original_valid_cells": 16 + len(completed), "original_expected_cells": 23, "missing_original_cell": 17, "suffix_terminal_failures": [cell["sequence"] for cell in failures], "valid_cells_by_arm": arm_valid, "expected_valid_cells_by_arm_if_suffix_completes": {"none": 8, "current_full": 8, "strictness_only": 7}, "intact_repeatability_units": intact_repeatability_units, "expected_intact_repeatability_units_if_suffix_completes": 11, "total_original_repeatability_units": 12, "input_arm_units": unit_table, "equal_weight_per_input_arm": True, "no_imputation": True}, "repair_sensitivity": {"status": repair_status, "logical_sample_id": "preface-cell-0017", "separate_from_primary": True}, "automatic_wording_decision": False}
    _atomic(root / PUBLIC_SETTLEMENT, summary); return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path); parser.add_argument("private_root", type=Path); parser.add_argument("original_work", type=Path); parser.add_argument("original_private", type=Path)
    for name in ("prepare", "capacity_preflight", "execute_one", "render_next_disclosure", "repair_cell17", "render_repair_disclosure", "settle_offline"): parser.add_argument("--" + name.replace("_", "-"), action="store_true")
    parser.add_argument("--full-regrade", action="store_true"); parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args(); chosen = [name for name in ("prepare", "capacity_preflight", "execute_one", "render_next_disclosure", "repair_cell17", "render_repair_disclosure", "settle_offline") if getattr(args, name)]
    if len(chosen) != 1: parser.error("choose exactly one action")
    common = (args.work, args.private_root, args.original_work, args.original_private)
    if args.prepare: result = prepare(*common)
    elif args.capacity_preflight: result = run_capacity_preflight(*common, allow_remote=args.allow_remote, timeout=args.timeout)
    elif args.execute_one: result = execute_one(*common, allow_remote=args.allow_remote, timeout=args.timeout)
    elif args.render_next_disclosure: result = render_next_disclosure(*common)
    elif args.repair_cell17: result = repair_cell17(*common, allow_remote=args.allow_remote, full_regrade=args.full_regrade, timeout=args.timeout)
    elif args.render_repair_disclosure: result = render_repair_disclosure(*common, full_regrade=args.full_regrade)
    else: result = settle_offline(*common)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__": main()
