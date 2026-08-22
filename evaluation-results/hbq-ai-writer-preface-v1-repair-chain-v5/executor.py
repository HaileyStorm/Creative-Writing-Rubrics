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
V4 = HERE.parent / "hbq-ai-writer-preface-v1-repair-chain-v4"
CONTRACT_PATH = HERE / "study-contract.json"
PUBLIC_BINDING, PUBLIC_DISCLOSURES, PUBLIC_JOURNAL, PUBLIC_SETTLEMENT = "recovery-binding.json", "outbound-disclosures.jsonl", "recovery-journal.jsonl", "offline-settlement.json"
PRIVATE_ATTEMPT = "recovery-attempt/terminal.json"
MODEL, REASONING, PROVIDER = "gpt-5.6-sol", "high", "codex"
ATTEMPT_ID = "cell17-quote-recovery-v5-01"
LEAF = "craft.narrative.point_of_view_and_focalization.distance"
LOCKED = {"question_id": LEAF, "verdict": "NO", "confidence": 0.99}


def _canonical(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
def _sha(value: bytes | str) -> str: return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()
def _fingerprint(path: Path) -> dict[str, Any]:
    data = path.read_bytes(); return {"bytes": len(data), "sha256": _sha(data)}
def _json(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error: raise ValueError(f"Invalid JSON object: {path}") from error
    if not isinstance(value, dict): raise ValueError(f"Invalid JSON object: {path}")
    return value
def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_suffix(path.suffix + ".tmp"); temporary.write_bytes(_canonical(value) + b"\n"); os.replace(temporary, path)
def _append(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as output: output.write(_canonical(value) + b"\n")
def _disjoint(*roots: Path) -> bool:
    resolved = [root.resolve() for root in roots]
    return all(not (left == right or left in right.parents or right in left.parents) for index, left in enumerate(resolved) for right in resolved[index + 1:])


def _v4() -> Any:
    name = "hbq_preface_recovery_v4_for_v5"; module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, V4 / "executor.py")
        if spec is None or spec.loader is None: raise ValueError("v4 executor cannot be loaded")
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    value = _json(CONTRACT_PATH)
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-ai-writer-preface-v1-repair-chain-v5" or value.get("locked_leaf") != LOCKED: raise ValueError("v5 recovery contract drifted")
    if value.get("recovery", {}).get("kind") != "pre_contact_infrastructure_recovery" or value.get("recovery", {}).get("max_additional_attempts") != 1: raise ValueError("v5 recovery cap drifted")
    return value


def _require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or _sha(path.read_bytes()) != expected: raise ValueError(f"{label} drifted")


def _verify_v4(v4_work: Path, v4_private: Path, v3_work: Path, v3_private: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> tuple[Any, dict[str, Any]]:
    parent, _binding = _v4()._verify(v4_work, v4_private, v3_work, v3_private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)
    lineage = contract()["lineage"]; settlement_path, terminal_path = v4_work / "offline-settlement.json", v4_private / "recovery-attempt" / "terminal.json"
    _require_hash(settlement_path, str(lineage["v4_public_settlement_sha256"]), "v4 public settlement"); _require_hash(terminal_path, str(lineage["v4_private_failed_terminal_sha256"]), "v4 private terminal")
    settlement, terminal = _json(settlement_path), _json(terminal_path)
    if settlement.get("study_id") != "hbq-ai-writer-preface-v1-repair-chain-v4" or terminal.get("status") != "terminal_failure_or_uncertain": raise ValueError("v4 lineage is not a sealed pre-contact failure")
    if terminal.get("failed_leaf_id") != LEAF or terminal.get("locked") != LOCKED or terminal.get("v3_lineage_is_not_a_vote") is not True: raise ValueError("v4 lineage does not bind the locked pre-contact failure")
    return parent, {"public_settlement": _fingerprint(settlement_path), "private_failed_terminal": _fingerprint(terminal_path), "classification": "pre_contact_infrastructure_recovery"}


def _binding(*parents: Path) -> dict[str, Any]:
    _parent, v4_lineage = _verify_v4(*parents)
    return {"format_version": 1, "study_id": contract()["study_id"], "contract": _fingerprint(CONTRACT_PATH), "executor": _fingerprint(HERE / "executor.py"), "v4_lineage": v4_lineage, "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "parents": "read-only evidence; this package never writes them"}


def prepare(work: Path, private: Path, v4_work: Path, v4_private: Path, v3_work: Path, v3_private: Path, original_work: Path, original_private: Path, continuation_work: Path, continuation_private: Path, v2_work: Path, v2_private: Path) -> dict[str, Any]:
    roots = tuple(path.resolve() for path in (work, private, v4_work, v4_private, v3_work, v3_private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private))
    if not _disjoint(*roots) or (roots[0].exists() and any(roots[0].iterdir())) or (roots[1].exists() and any(roots[1].iterdir())): raise ValueError("Recovery roots must be fresh and pairwise disjoint")
    roots[0].mkdir(parents=True, exist_ok=True); roots[1].mkdir(parents=True, exist_ok=True); _atomic(roots[0] / PUBLIC_BINDING, _binding(*roots[2:]))
    return {"provider_calls": 0, "status": "prepared", "max_additional_attempts": 1}


def _verify(work: Path, private: Path, *parents: Path) -> tuple[Any, dict[str, Any]]:
    roots = tuple(path.resolve() for path in (work, private, *parents))
    if not _disjoint(*roots): raise ValueError("Recovery roots must remain pairwise disjoint")
    expected = _binding(*roots[2:])
    if _json(roots[0] / PUBLIC_BINDING) != expected: raise ValueError("Prepared recovery binding drifted")
    return _verify_v4(*roots[2:])[0], expected


def _disclosure(prompt: str) -> dict[str, Any]:
    return {"event": "pre_contact_infrastructure_recovery_disclosure", "destination": "Codex CLI -> authenticated OpenAI service", "provider": {"provider": PROVIDER, "model": MODEL, "reasoning": REASONING}, "repair_attempt_id": ATTEMPT_ID, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": LEAF, "locked": LOCKED, "outbound_content": "Locked leaf, generated artifact and context only; no private execution evidence.", "prompt_sha256": _sha(prompt), "paid_api": False, "human_judgment": False}
def _terminal(private: Path) -> dict[str, Any] | None:
    path = private / PRIVATE_ATTEMPT; return _json(path) if path.is_file() else None


def render_next_disclosure(work: Path, private: Path, *parents: Path) -> dict[str, Any]:
    parent, _ = _verify(work, private, *parents)
    if _terminal(private.resolve()) is not None: return {"provider_calls": 0, "status": "settled"}
    _cell, _item, prompt = _v4()._item_and_prompt(parent, parents[5].resolve())
    return {"provider_calls": 0, "status": "pending", "disclosure": _disclosure(prompt), "exact_rendered_prompt": prompt}


def execute_one(work: Path, private: Path, *parents: Path, allow_remote: bool = False, timeout: float = 3600.0) -> dict[str, Any]:
    parent, _ = _verify(work, private, *parents)
    if not allow_remote: raise ValueError("Recovery execution sends disclosed writing; pass --allow-remote after review")
    root, private_root = work.resolve(), private.resolve()
    if _terminal(private_root) is not None: return {"provider_calls": 0, "status": "settled"}
    _cell, item, prompt = _v4()._item_and_prompt(parent, parents[5].resolve()); _append(root / PUBLIC_DISCLOSURES, _disclosure(prompt)); attempt_dir = (private_root / PRIVATE_ATTEMPT).parent
    try: attempt_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError: return {"provider_calls": 0, "status": "claimed"}
    try:
        response, provider_record = parent._runner()._call_codex(executable="codex", model=MODEL, reasoning=REASONING, prompt=prompt, output_dir=attempt_dir, response_schema=parent.SCHEMA_PATH, batch_number=1, timeout=timeout, attempt_number=1)
        payload = parent._runner()._parse_model_json(response); valid = _v4()._v3()._valid_quote(payload, item); normalized: list[Any] = []; status = "invalid_quote_repair"
        if valid:
            normalized = parent._runner()._normalize_batch(payload, expected_ids=[LEAF], artifact_id=str(item["item_id"]), bundle_id="prose.short_story", judge_id=f"{PROVIDER}:{MODEL}", run_id=ATTEMPT_ID, artifact_text=Path(str(item["artifact"]["path"])).read_text(encoding="utf-8-sig"), context_texts=[Path(str(value["path"])).read_text(encoding="utf-8-sig") for value in item["contexts"]]); status = "valid_quote_repair"
        terminal = {"format_version": 1, "status": status, "repair_attempt_id": ATTEMPT_ID, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": LEAF, "locked": LOCKED, "response": response, "response_sha256": _sha(response), "provider_record": provider_record, "provider_record_sha256": _sha(_canonical(provider_record)), "normalized_verdicts": normalized, "normalized_verdicts_sha256": _sha(_canonical(normalized)), "v4_lineage_is_not_a_vote": True}
    except Exception as error:
        response = getattr(error, "content", ""); terminal = {"format_version": 1, "status": "terminal_failure_or_uncertain", "repair_attempt_id": ATTEMPT_ID, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": LEAF, "locked": LOCKED, "response": response if isinstance(response, str) else "", "response_sha256": _sha(response if isinstance(response, str) else ""), "error": str(error), "error_sha256": _sha(str(error)), "v4_lineage_is_not_a_vote": True}
    _atomic(private_root / PRIVATE_ATTEMPT, terminal); _append(root / PUBLIC_JOURNAL, {"event": terminal["status"], "repair_attempt_id": ATTEMPT_ID, "private_terminal_sha256": _sha((private_root / PRIVATE_ATTEMPT).read_bytes())})
    return {"provider_calls": 1, "status": terminal["status"], "repair_attempt_id": ATTEMPT_ID}


def settle_offline(work: Path, private: Path, *parents: Path) -> dict[str, Any]:
    _parent, binding = _verify(work, private, *parents); terminal = _terminal(private.resolve())
    summary = {"format_version": 1, "study_id": contract()["study_id"], "provider_calls": 0, "binding_sha256": _sha(_canonical(binding)), "v4_lineage": {"classification": "pre_contact_infrastructure_recovery", "counts_as_vote": False, "counts_as_repair": False}, "recovery": {"max_additional_attempts": 1, "attempts": 1 if terminal else 0, "status": terminal.get("status") if terminal else "pending", "locked": LOCKED}, "primary_analysis": {"original_valid_cells": 22, "original_expected_cells": 23, "missing_original_cell": 17, "no_imputation": True}}
    _atomic(work.resolve() / PUBLIC_SETTLEMENT, summary); return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "private", "v4_work", "v4_private", "v3_work", "v3_private", "original_work", "original_private", "continuation_work", "continuation_private", "v2_work", "v2_private"): parser.add_argument(name, type=Path)
    for name in ("prepare", "render_next_disclosure", "execute_one", "settle_offline"): parser.add_argument("--" + name.replace("_", "-"), action="store_true")
    parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--timeout", type=float, default=3600.0); args = parser.parse_args()
    actions = [name for name in ("prepare", "render_next_disclosure", "execute_one", "settle_offline") if getattr(args, name)]
    if len(actions) != 1: parser.error("choose exactly one action")
    common = (args.work, args.private, args.v4_work, args.v4_private, args.v3_work, args.v3_private, args.original_work, args.original_private, args.continuation_work, args.continuation_private, args.v2_work, args.v2_private)
    result = prepare(*common) if args.prepare else render_next_disclosure(*common) if args.render_next_disclosure else execute_one(*common, allow_remote=args.allow_remote, timeout=args.timeout) if args.execute_one else settle_offline(*common)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__": main()
