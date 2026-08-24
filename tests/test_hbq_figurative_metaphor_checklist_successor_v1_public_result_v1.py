from __future__ import annotations

from copy import deepcopy
import json
import re

import pytest

from hbqrs.paths import book_root


ROOT = (
    book_root()
    / "evaluation-results"
    / "hbq-figurative-metaphor-checklist-successor-v1-execution-v1-public-result-v1"
)

EXPECTED_BINDINGS = {
    "execution_claim_sha256": "e9aa0e3845372772e9175a0e868d7f3f2b338c6b7db221ba30aef97921c55d02",
    "runtime_schedule_sha256": "caf594b7ee3d812a3d8828b1101137459f2555e7ac0557f00b5559660888f4c3",
    "settlement_sha256": "3d7dc71d1e16d4181a4aeb235f95bc877bbe9dab600f1b52bd21890a6ddd59a2",
    "public_aggregate_sha256": "bcc535d4deae721f27a49f7a67d27d2f98cb0e9bb4365a5b114ed64b75b32312",
    "terminal_sidecar_sha256": "632ac337aacc3a589fb58093b0b6e6ad200859083567284e6bf2970491eed637",
}


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def _validate(value: dict) -> None:
    if set(value) != {
        "format_version",
        "study_id",
        "source_bindings",
        "execution",
        "aggregate",
        "decision",
        "interpretation",
        "phase_b_enabled",
        "real_holdout_opened",
        "promotion",
        "ownership",
        "dspy",
    }:
        raise ValueError("public-result schema drift")
    if value["format_version"] != 1:
        raise ValueError("format version drift")
    if value["study_id"] != "hbq-figurative-metaphor-checklist-successor-v1-execution-v1":
        raise ValueError("study identity drift")
    if value["source_bindings"] != EXPECTED_BINDINGS:
        raise ValueError("source binding drift")
    if not all(re.fullmatch(r"[0-9a-f]{64}", item) for item in value["source_bindings"].values()):
        raise ValueError("invalid source commitment")
    if value["execution"] != {
        "planned_calls": 72,
        "completed_calls": 72,
        "first_attempt_accepted_calls": 72,
    }:
        raise ValueError("execution count drift")
    if value["aggregate"] != {
        "target": {
            "correct": 12,
            "total": 24,
            "distinct_wording": 3,
            "distinct_stockness_load_strata": 3,
            "mixed_cells": 2,
            "stable_all_wrong_cells": 3,
        },
        "controls": {
            "no_default_metaphors": {"correct": 12, "total": 24, "passed": False},
            "purple_prose_proportion": {"correct": 14, "total": 24, "passed": False},
        },
    }:
        raise ValueError("aggregate drift")
    if value["decision"] != "FIXTURE_OR_OWNERSHIP_INVALID_NO_GO":
        raise ValueError("decision drift")
    if value["interpretation"] != (
        "The shared synthetic fixtures do not isolate the target and control concerns, "
        "so no target-wording conclusion follows."
    ):
        raise ValueError("interpretation drift")
    if value["phase_b_enabled"] is not False or value["real_holdout_opened"] is not False:
        raise ValueError("phase stop drift")
    if value["promotion"] != "none":
        raise ValueError("promotion drift")
    if value["ownership"] != {
        "stockness": "core.freshness_and_non_genericness.no_default_metaphors",
        "figurative_density": "penalty.purple_prose.proportion",
    }:
        raise ValueError("ownership drift")
    if value["dspy"] != "not_used_development_only_fallback":
        raise ValueError("DSPy status drift")


def test_public_result_has_exact_schema_counts_and_commitments() -> None:
    _validate(_result())


def test_public_result_rejects_semantic_and_binding_tampering() -> None:
    original = _result()
    for mutate in (
        lambda value: value["execution"].update({"completed_calls": 71}),
        lambda value: value["aggregate"]["controls"]["no_default_metaphors"].update({"correct": 24}),
        lambda value: value.update({"decision": "PROMOTION_REVIEW_ELIGIBLE"}),
        lambda value: value.update({"phase_b_enabled": True}),
        lambda value: value["ownership"].update({"stockness": "target"}),
        lambda value: value["source_bindings"].update({"settlement_sha256": "0" * 64}),
    ):
        changed = deepcopy(original)
        mutate(changed)
        with pytest.raises(ValueError):
            _validate(changed)


def test_public_projection_excludes_private_execution_material_and_paths() -> None:
    package = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("README.md", "public-result.json")
    ).lower()

    assert not re.search(r"[a-z]:[\\/]", package)
    forbidden = (
        "expected_ledger",
        "exact_quote",
        "raw_response",
        "session_id",
        "request_id",
        "slot_id",
        "case_id",
        "fixture_alias",
    )
    assert all(token not in package for token in forbidden)
