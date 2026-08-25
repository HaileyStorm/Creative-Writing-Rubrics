"""Provider-free contract for development-only whole-poem DSPy work."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-poetry-whole-poem-architecture-dspy-v1"
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
TRAIN_CASES = 12
DEV_CASES = 8
PHYSICAL_COMPILE_SEND_CAP = 64
PRODUCTION_TRANSFER_CALLS = 16


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(name: str) -> dict[str, Any]:
    value = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {name}")
    return value


def load_contract() -> dict[str, Any]:
    return load_json("study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json("public-synthetic-corpus.json")


def validate_grounded_four_state(*, expected: str, observed: str, evidence: str, artifact_text: str) -> bool:
    """Exact development metric: state equality plus an evidence span in the input."""
    if expected not in VERDICTS or observed not in VERDICTS:
        raise ValueError("Four-state verdict required")
    if not isinstance(evidence, str) or not evidence.strip() or evidence not in artifact_text:
        raise ValueError("Grounding must quote a nonempty artifact span")
    return expected == observed


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "future_holdout", "cases"}:
        raise ValueError("Corpus surface drifted")
    if corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only" or corpus["future_holdout"] is not False:
        raise ValueError("Corpus identity or holdout boundary drifted")
    cases = corpus["cases"]
    fields = {"case_id", "split", "artifact_type", "declared_scope", "completion_status", "fixture_origin", "text", "expected_verdict", "grounding"}
    if not isinstance(cases, list) or len(cases) != TRAIN_CASES + DEV_CASES:
        raise ValueError("Exact TRAIN and DEV geometry required")
    ids: set[str] = set()
    texts: set[str] = set()
    counts = {"TRAIN": 0, "DEV": 0}
    descendants = 0
    for case in cases:
        if not isinstance(case, dict) or set(case) != fields:
            raise ValueError("Corpus case shape drifted")
        case_id, split, text = case["case_id"], case["split"], case["text"]
        if not isinstance(case_id, str) or not case_id or case_id in ids or not isinstance(text, str) or not text or text in texts:
            raise ValueError("Corpus cases must be unique public synthetic artifacts")
        if split not in counts or case["artifact_type"] != "poetry" or case["fixture_origin"] not in {"new_public_synthetic", "new_public_synthetic_clear_descendant"}:
            raise ValueError("Corpus split, type, or lineage drifted")
        validate_grounded_four_state(expected=case["expected_verdict"], observed=case["expected_verdict"], evidence=case["grounding"], artifact_text=text)
        ids.add(case_id)
        texts.add(text)
        counts[split] += 1
        descendants += case["fixture_origin"] == "new_public_synthetic_clear_descendant"
    if counts != {"TRAIN": TRAIN_CASES, "DEV": DEV_CASES} or descendants != 6:
        raise ValueError("Frozen public-synthetic split or descendant replacement drifted")
    train_ids = {case["case_id"] for case in cases if case["split"] == "TRAIN"}
    dev_ids = {case["case_id"] for case in cases if case["split"] == "DEV"}
    if train_ids & dev_ids:
        raise ValueError("TRAIN and DEV must remain disjoint")
    states = {case["expected_verdict"] for case in cases}
    if states != VERDICTS:
        raise ValueError("All four response states must remain represented")


def static_export_words() -> list[str]:
    return (ROOT / "static-export.txt").read_text(encoding="utf-8").split()


def verify_static_export() -> None:
    text = (ROOT / "static-export.txt").read_text(encoding="utf-8")
    if not text.strip() or len(static_export_words()) > 180:
        raise ValueError("Static export must be nonempty and at most 180 words")
    words = set(re.findall(r"[A-Za-z_]+", text.casefold()))
    prohibited = ("yes", "no", "not_applicable", "cannot_assess", "train", "dev", "fixture", "runtime", "model", "call", "retry", "prompt")
    if words & set(prohibited):
        raise ValueError("Static export contains a forbidden label, fixture phrase, or runtime direction")


def production_transfer_plan() -> list[dict[str, Any]]:
    dev = [case for case in load_corpus()["cases"] if case["split"] == "DEV"]
    return [
        {"slot_id": f"architecture-dspy-transfer-{index:03d}-{pass_number}", "case_id": case["case_id"], "pass": pass_number}
        for index, case in enumerate(dev, start=1)
        for pass_number in (1, 2)
    ]


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "dspy", "corpus", "optimizer", "metric", "static_export", "terminal_settlement", "transfer_gate", "promotion", "private_bindings", "forbidden"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "FROZEN_PROVIDER_FREE" or contract["development_only"] is not True:
        raise ValueError("Contract identity drifted")
    if contract["dspy"] != {"version": "3.3.0", "scope": "private_development_venv_only", "runtime_dependency": "forbidden"}:
        raise ValueError("DSPy boundary drifted")
    if contract["corpus"] != {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json"), "train_cases_exact": TRAIN_CASES, "dev_cases_exact": DEV_CASES, "future_holdout": False}:
        raise ValueError("Corpus binding drifted")
    if contract["optimizer"] != {"kind": "MIPROv2", "program": "Predict", "instruction_only": True, "demos_exact": 0, "bootstrap": "overridden_to_none", "data_aware_proposer": False, "fewshot_aware_proposer": False, "auto": None, "seed": 20260825, "num_candidates": 4, "num_trials": 4, "threads": 1, "retries": 0, "physical_compile_send_cap": PHYSICAL_COMPILE_SEND_CAP}:
        raise ValueError("Optimizer freeze drifted")
    if contract["metric"] != {"name": "exact_four_state_plus_grounding", "states": ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"], "grounding": "nonempty_exact_substring", "aggregation": "all_cases_exact", "expected_labels_provider_visible": False}:
        raise ValueError("Metric freeze drifted")
    if contract["static_export"] != {"path": "static-export.txt", "sha256": sha256_file(ROOT / "static-export.txt"), "max_words": 180, "demos": 0, "labels": "excluded", "fixture_phrases": "excluded", "runtime_directions": "excluded"}:
        raise ValueError("Static export binding drifted")
    if contract["terminal_settlement"] != {"compiled_static_export_path": "compiled-static-export.txt", "completed_requires_export_before_terminal": True, "bind_relative_path_hash_word_count": True, "resume_or_overwrite": "forbidden"}:
        raise ValueError("Terminal settlement binding drifted")
    if contract["transfer_gate"] != {"production_calls_exact": PRODUCTION_TRANSFER_CALLS, "dev_cases_exact": DEV_CASES, "passes_per_case_exact": 2, "allowed_only_after_separate_review": True, "provider": "codex_chatgpt_subscription", "model": "gpt-5.6-sol", "reasoning": "high", "canonical_runner_call": "src/hbqrs/runner.py::_call_codex", "paid_api_or_fallback": "forbidden"}:
        raise ValueError("Transfer gate drifted")
    if contract["promotion"] != {"on_transfer_pass": "candidate_for_manual_review_only", "prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "weight": "none", "release": "none"}:
        raise ValueError("Promotion boundary drifted")
    if set(contract["private_bindings"]) != {"engine_sha256", "freeze_inputs_sha256", "environment_evidence_sha256"} or not all(isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value) for value in contract["private_bindings"].values()):
        raise ValueError("Private binding commitment malformed")
    forbidden = {"provider_execution_before_review", "paid_api_or_fallback", "runtime_dspy_dependency", "demos", "future_holdout", "automatic_promotion", "provider_visible_expected_labels"}
    if set(contract["forbidden"]) != forbidden:
        raise ValueError("Forbidden surface drifted")
    verify_corpus(load_corpus())
    verify_static_export()
    transfer = production_transfer_plan()
    if len(transfer) != PRODUCTION_TRANSFER_CALLS or len({slot["slot_id"] for slot in transfer}) != PRODUCTION_TRANSFER_CALLS:
        raise ValueError("Exact production transfer geometry drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "train_cases": TRAIN_CASES, "dev_cases": DEV_CASES, "transfer_calls": len(transfer)}
