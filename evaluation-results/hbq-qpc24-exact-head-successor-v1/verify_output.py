"""Verify QPC24's aggregate-only public preexecution projection."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
AGGREGATE = HERE / "qpc24-public-aggregate-plan.v1.json"
FORBIDDEN = (
    ("Windows path", r"[A-Za-z]:[\\/]"), ("home path", r"(?:^|[\\/])(?:Users|home)(?:[\\/]|$)"),
    ("private prose", r"Chapter One|Part One|PRIVATE_PROSE_SENTINEL"),
    ("rendered prompt", r"BEGIN UNTRUSTED FROZEN TASK-CONTRACT"),
    ("expected label", r"expected_state"), ("model output", r"raw_response|verdicts"),
    ("session identifier", r"session_id"), ("request identifier", r"request_id"),
    ("per-call identifier", r"slot_id|batch_number"),
)


def _study():
    spec = importlib.util.spec_from_file_location("hbq_qpc24_exact_head_successor_v1", HERE / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(root: Path = HERE) -> list[str]:
    failures: list[str] = []
    try:
        data = json.loads((root / AGGREGATE.name).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [f"aggregate is unreadable: {error}"]
    study = _study()
    expected = {
        "format_version": 1, "study_id": study.STUDY_ID, "source_head": study.HEAD,
        "status": "FROZEN_PROVIDER_FREE_PREEXECUTION", "artifact_roles": list(study.ROLE_ORDER),
        "protocol_geometry": {"complete_eligible_questions": 221, "questions_per_provider_call": 24, "full_batches_per_logical_work": 9, "remainder_questions": 5, "remainder_batches_per_logical_work": 1, "repetitions_per_role": 5, "logical_work_evaluations": 15, "planned_provider_calls": 150, "verdict_positions": 3315},
        "provider_calls_made": 0, "future_execution": "separate_exact_binding_review_required",
        "immutability": {"retry": "forbidden", "resume": "forbidden", "post_holdout_iteration": "forbidden"},
        "commitments": {"study_contract_sha256": study.sha256_bytes((root / "study-contract.json").read_bytes())},
        "privacy": "Aggregate-only projection: no private prose, rendered prompts, expected labels, model outputs, local paths, sessions, requests, or per-call records.",
        "non_claims": ["No rubric or prompt promotion.", "No provider execution, paid evaluation, or human judging.", "No Gray Blood rebaseline is opened by this package."],
    }
    if data != expected:
        failures.append("aggregate shape or commitments drifted")
    text = (root / AGGREGATE.name).read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN:
        if re.search(pattern, text, flags=re.IGNORECASE):
            failures.append(f"forbidden aggregate-only content: {label}")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("QPC24 public aggregate verification failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("QPC24 public aggregate verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
