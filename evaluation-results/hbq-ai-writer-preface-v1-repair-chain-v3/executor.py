"""One sealed post-infrastructure recovery call for preface cell 17."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
ORIGINAL = HERE.parent / "hbq-ai-writer-preface-v1-pilot-executor-v1"
CONTINUATION = HERE.parent / "hbq-ai-writer-preface-v1-continuation-v1"
CONTRACT_PATH = HERE / "study-contract.json"
PUBLIC_BINDING = "recovery-binding.json"
PUBLIC_DISCLOSURES = "outbound-disclosures.jsonl"
PUBLIC_JOURNAL = "recovery-journal.jsonl"
PUBLIC_SETTLEMENT = "offline-settlement.json"
PRIVATE_ATTEMPT = "recovery-attempt/terminal.json"
MODEL, REASONING, PROVIDER = "gpt-5.6-sol", "high", "codex"
ATTEMPT_ID = "cell17-quote-recovery-v3-01"
LEAF = "craft.narrative.point_of_view_and_focalization.distance"
LOCKED = {"question_id": LEAF, "verdict": "NO", "confidence": 0.99}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON object: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Invalid JSON object: {path}")
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


def _fingerprint(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": _sha(data)}


def _disjoint(*roots: Path) -> bool:
    resolved = [root.resolve() for root in roots]
    return all(not (left == right or left in right.parents or right in left.parents) for index, left in enumerate(resolved) for right in resolved[index + 1:])


def _continuation() -> Any:
    name = "hbq_preface_continuation_for_recovery_v3"
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
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-ai-writer-preface-v1-repair-chain-v3":
        raise ValueError("Recovery contract drifted")
    if value.get("recovery", {}).get("max_additional_attempts") != 1 or value.get("recovery", {}).get("kind") != "pre_contact_infrastructure_recovery":
        raise ValueError("Recovery cap drifted")
    if value.get("locked_leaf") != LOCKED:
        raise ValueError("Recovery lock drifted")
    return value


def _require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or _sha(path.read_bytes()) != expected:
        raise ValueError(f"{label} drifted")


def _verify_v2(v2_work: Path, v2_private: Path) -> dict[str, Any]:
    lineage = contract()["lineage"]
    settlement_path = v2_work / "offline-settlement.json"
    terminal_path = v2_private / "repair-attempts" / "01" / "terminal.json"
    _require_hash(settlement_path, str(lineage["v2_public_settlement_sha256"]), "v2 public settlement")
    _require_hash(terminal_path, str(lineage["v2_private_failed_terminal_sha256"]), "v2 failed terminal")
    settlement, terminal = _json(settlement_path), _json(terminal_path)
    if settlement.get("study_id") != "hbq-ai-writer-preface-v1-repair-chain-v2" or terminal.get("status") != "terminal_failure_or_uncertain":
        raise ValueError("v2 lineage is not the sealed infrastructure failure")
    if terminal.get("failed_leaf_id") != LEAF or terminal.get("locked") != LOCKED or terminal.get("provider_attestation") != "unavailable":
        raise ValueError("v2 lineage does not bind the locked pre-contact failure")
    return {"public_settlement": _fingerprint(settlement_path), "private_failed_terminal": _fingerprint(terminal_path), "classification": "pre_contact_infrastructure_recovery"}


def _verify_parents(original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> tuple[Any, dict[str, Any]]:
    continuation = _continuation()
    continuation._verify(continuation_work, continuation_private, original_work, original_private)
    original_terminal = _json(original_private / "cells" / "0017" / "terminal.json")
    if original_terminal.get("status") != "terminal_failure_or_uncertain" or original_terminal.get("cell", {}).get("sequence") != 17:
        raise ValueError("Original cell 17 drifted")
    return continuation._parent(), _verify_v2(v2_work, v2_private)


def _binding(original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> dict[str, Any]:
    _parent, v2 = _verify_parents(original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)
    return {"format_version": 1, "study_id": contract()["study_id"], "contract": _fingerprint(CONTRACT_PATH), "executor": _fingerprint(HERE / "executor.py"), "v2_lineage": v2, "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "parents": "read-only evidence; this package never writes them"}


def prepare(work: Path, private: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> dict[str, Any]:
    roots = tuple(path.resolve() for path in (work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private))
    if not _disjoint(*roots) or (roots[0].exists() and any(roots[0].iterdir())) or (roots[1].exists() and any(roots[1].iterdir())):
        raise ValueError("Recovery roots must be fresh and pairwise disjoint")
    roots[0].mkdir(parents=True, exist_ok=True); roots[1].mkdir(parents=True, exist_ok=True)
    _atomic(roots[0] / PUBLIC_BINDING, _binding(*roots[2:]))
    return {"provider_calls": 0, "status": "prepared", "max_additional_attempts": 1}


def _verify(work: Path, private: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> tuple[Any, dict[str, Any]]:
    roots = tuple(path.resolve() for path in (work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private))
    if not _disjoint(*roots):
        raise ValueError("Recovery roots must remain pairwise disjoint")
    expected = _binding(*roots[2:])
    if _json(roots[0] / PUBLIC_BINDING) != expected:
        raise ValueError("Prepared recovery binding drifted")
    return _verify_parents(*roots[2:])[0], expected


def _item_and_prompt(parent: Any, original_private: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    terminal = _json(original_private / "cells" / "0017" / "terminal.json")
    item = parent._item(original_private, str(terminal["cell"]["item_id"]))
    rows = _json(original_private / "cells" / "0017" / "responses" / "batch-0001.attempt-0001.message.json")["verdicts"]
    source = next((row for row in rows if row.get("question_id") == LEAF), None)
    if source is None or {key: source.get(key) for key in LOCKED} != LOCKED:
        raise ValueError("Original leaf lock drifted")
    questions, _ = parent._compiled_questions(item)
    question = next((entry["question"] for entry in questions if entry["question"]["id"] == LEAF), None)
    if question is None:
        raise ValueError("Locked leaf is absent from the compiled sequence")
    artifact = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig")
    contexts = [Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]]
    prompt = "\n\n".join(("Return one complete canonical HBQ verdict for this question only. Do not change the locked verdict or confidence. Use a nonempty exact quote that occurs verbatim in the supplied artifact or context.", "LOCKED ORIGINAL: " + json.dumps(LOCKED, sort_keys=True), "QUESTION: " + json.dumps(question, ensure_ascii=False, sort_keys=True), "ARTIFACT:\n" + artifact, "CONTEXT:\n" + "\n\n".join(contexts)))
    return terminal["cell"], item, prompt


def _disclosure(prompt: str) -> dict[str, Any]:
    return {"event": "pre_contact_infrastructure_recovery_disclosure", "destination": "Codex CLI -> authenticated OpenAI service", "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "repair_attempt_id": ATTEMPT_ID, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": LEAF, "locked": LOCKED, "outbound_content": "Locked leaf, generated artifact and context only; no private execution evidence.", "prompt_sha256": _sha(prompt), "paid_api": False, "human_judgment": False}


def _terminal(private: Path) -> dict[str, Any] | None:
    path = private / PRIVATE_ATTEMPT
    return _json(path) if path.is_file() else None


def _valid_quote(payload: object, item: Mapping[str, Any]) -> bool:
    rows = payload.get("verdicts") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or {key: rows[0].get(key) for key in LOCKED} != LOCKED:
        return False
    evidence = rows[0].get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    source = Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig") + "\n" + "\n".join(Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"])
    return all(isinstance(entry, dict) and entry.get("kind") == "exact_quote" and isinstance(entry.get("exact_quote"), str) and bool(entry["exact_quote"].strip()) and entry["exact_quote"] in source for entry in evidence)


def render_next_disclosure(work: Path, private: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> dict[str, Any]:
    parent, _ = _verify(work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)
    existing = _terminal(private.resolve())
    if existing is not None:
        return {"provider_calls": 0, "status": "settled", "terminal_status": existing.get("status")}
    _cell, _item, prompt = _item_and_prompt(parent, original_private.resolve())
    return {"provider_calls": 0, "status": "pending", "disclosure": _disclosure(prompt), "exact_rendered_prompt": prompt}


def execute_one(work: Path, private: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path, *, allow_remote: bool = False, timeout: float = 3600.0) -> dict[str, Any]:
    parent, _ = _verify(work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)
    if not allow_remote:
        raise ValueError("Recovery execution sends disclosed writing; pass --allow-remote after review")
    root, private_root = work.resolve(), private.resolve()
    if _terminal(private_root) is not None:
        return {"provider_calls": 0, "status": "settled"}
    cell, item, prompt = _item_and_prompt(parent, original_private.resolve())
    _append(root / PUBLIC_DISCLOSURES, _disclosure(prompt))
    attempt_dir = (private_root / PRIVATE_ATTEMPT).parent
    attempt_dir.mkdir(parents=True, exist_ok=False)
    try:
        response, provider_record = parent._runner()._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=attempt_dir, response_schema=parent.SCHEMA_PATH, batch_number=1, timeout=timeout, attempt_number=1)
        payload = parent._runner()._parse_model_json(response)
        valid = _valid_quote(payload, item)
        normalized: list[Any] = []
        status = "invalid_quote_repair"
        if valid:
            normalized = parent._runner()._normalize_batch(payload, expected_ids=[LEAF], artifact_id=str(item["item_id"]), bundle_id="prose.short_story", judge_id=f"{PROVIDER}:{MODEL}", run_id=ATTEMPT_ID, artifact_text=Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig"), context_texts=[Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]])
            status = "valid_quote_repair"
        terminal = {"format_version": 1, "status": status, "repair_attempt_id": ATTEMPT_ID, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": LEAF, "locked": LOCKED, "response": response, "response_sha256": _sha(response), "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)), "normalized_verdicts": normalized, "normalized_verdicts_sha256": _sha(_canonical(normalized)), "v2_lineage_is_not_a_vote": True}
    except Exception as error:
        response = getattr(error, "content", "")
        terminal = {"format_version": 1, "status": "terminal_failure_or_uncertain", "repair_attempt_id": ATTEMPT_ID, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": LEAF, "locked": LOCKED, "response": response if isinstance(response, str) else "", "response_sha256": _sha(response if isinstance(response, str) else ""), "error": str(error), "error_sha256": _sha(str(error)), "v2_lineage_is_not_a_vote": True}
    _atomic(private_root / PRIVATE_ATTEMPT, terminal)
    _append(root / PUBLIC_JOURNAL, {"event": terminal["status"], "repair_attempt_id": ATTEMPT_ID, "private_terminal_sha256": _sha((private_root / PRIVATE_ATTEMPT).read_bytes())})
    return {"provider_calls": 1, "status": terminal["status"], "repair_attempt_id": ATTEMPT_ID}


def settle_offline(work: Path, private: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> dict[str, Any]:
    _parent, binding = _verify(work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)
    terminal = _terminal(private.resolve())
    summary = {"format_version": 1, "study_id": contract()["study_id"], "provider_calls": 0, "binding_sha256": _sha(_canonical(binding)), "v2_lineage": {"classification": "pre_contact_infrastructure_recovery", "counts_as_vote": False, "counts_as_repair": False}, "recovery": {"max_additional_attempts": 1, "attempts": 1 if terminal else 0, "status": terminal.get("status") if terminal else "pending", "locked": LOCKED}, "primary_analysis": {"original_valid_cells": 22, "original_expected_cells": 23, "missing_original_cell": 17, "no_imputation": True}}
    _atomic(work.resolve() / PUBLIC_SETTLEMENT, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "private", "original_work", "original_private", "continuation_work", "continuation_private", "v2_work", "v2_private"):
        parser.add_argument(name, type=Path)
    for name in ("prepare", "render_next_disclosure", "execute_one", "settle_offline"):
        parser.add_argument("--" + name.replace("_", "-"), action="store_true")
    parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args(); actions = [name for name in ("prepare", "render_next_disclosure", "execute_one", "settle_offline") if getattr(args, name)]
    if len(actions) != 1: parser.error("choose exactly one action")
    common = (args.work, args.private, args.original_work, args.original_private, args.continuation_work, args.continuation_private, args.v2_work, args.v2_private)
    result = prepare(*common) if args.prepare else render_next_disclosure(*common) if args.render_next_disclosure else execute_one(*common, allow_remote=args.allow_remote, timeout=args.timeout) if args.execute_one else settle_offline(*common)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
