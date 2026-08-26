from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
AGGREGATE_NAME = "aggregate.v1.json"
ALLOWED_FILES = {"README.md", AGGREGATE_NAME, "verify_output.py"}
README_SHA256 = "a882761bf99fcf0f746f14f0b81e85e41495987c113b81650a2ebce7a9466263"
FORBIDDEN_FIELD_NAMES = {
    "absolute_path",
    "artifact_id",
    "cell",
    "cells",
    "exact_quote",
    "finding",
    "findings",
    "local_unit",
    "position_id",
    "prompt",
    "prose",
    "question_id",
    "raw_prompt",
    "raw_response",
    "response",
    "response_id",
    "row",
    "rows",
    "per_cell_row",
    "per_cell_rows",
    "run_id",
    "session_id",
    "unit_id",
    "warning",
    "warnings",
}
FORBIDDEN_TEXT_MARKERS = ("C:\\Users\\", "source.md", "prompt.md", "raw_response")
EXPECTED = {
    "artifacts": [
        {
            "binary_calls": {"accepted": 80, "planned": 80, "settled": 80},
            "coverage": 0.9883,
            "error_calls": 0,
            "label": "author_original",
            "local_unit_count": 7,
            "positions": 1817,
            "rejected_calls": 0,
            "score": 63.0202,
            "score_bounds": {"lower": 62.0577, "upper": 63.2243},
            "status": "VALID",
            "unit_count": 8,
        },
        {
            "binary_calls": {"accepted": 70, "planned": 70, "settled": 70},
            "coverage": 0.9905,
            "error_calls": 0,
            "label": "gpt_5_6_pro_rewrite",
            "local_unit_count": 6,
            "positions": 1589,
            "rejected_calls": 0,
            "score": 73.2369,
            "score_bounds": {"lower": 72.3575, "upper": 73.3054},
            "status": "VALID",
            "unit_count": 7,
        },
    ],
    "comparison": {
        "bounds_relation": "NON_STATISTICAL_NONOVERLAP",
        "score_difference_rewrite_minus_author": 10.2167,
    },
    "decision": {
        "criterion_ownership_changes": 0,
        "promotion": "NONE",
        "rubric_changes": 0,
        "weight_changes": 0,
    },
    "execution": {
        "combined_binary_calls": 150,
        "combined_positions": 3406,
        "full_fidelity": True,
        "prior_structured_calls": 6,
        "provider_calls": 0,
        "sampling": "NONE",
    },
    "format_version": 1,
    "opaque_execution_commitments": {
        "author_v7_inventory_sha256": "b73831ad6b8a6f8ac6d1f866464c49184637e0106c1e60b66f7562df20bf61a3",
        "author_v8_result_sha256": "0be746487e641abbb96fbcbad816162d9d56a559b9428cd5b5ac3c2d4f3695a7",
        "freeze_manifest_sha256": "e6fd66e1d3c1623135b582b3106cc372f26c48bd7116adeef8af3e5906c46048",
        "freeze_plan_sha256": "0761561b7a3fb02909d90b927830b2f3255edcdcfc666a9a39824d225a486241",
        "rewrite_v7_inventory_sha256": "b173ee56384dbeafbc5de05241b2d71c3883442fabab916a0cc2a76a19c74637",
        "rewrite_v8_result_sha256": "48c698541d9d61f736340ed2f5b6e7cf6382cff29dd4271fba61ee06bd10211d",
    },
    "runtime": {
        "cwr_commit": "56b01758e896e35a7936753c08829cd5fcf040bf",
        "cwr_runtime_version": "1.2.3",
        "hbq_rs_standard_version": "1.2.1",
    },
    "scope": "WORK_IN_PROGRESS_FULL_FIDELITY_REBASELINE",
    "study_id": "hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1",
}


def _read(root: Path) -> dict[str, Any]:
    value = json.loads((root / AGGREGATE_NAME).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Aggregate result must be an object")
    return value


def _walk(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_FIELD_NAMES:
                raise ValueError(f"Restricted public field: {key}")
            _walk(item)
    elif isinstance(value, list):
        for item in value:
            _walk(item)


def _assert_arithmetic(value: dict[str, Any]) -> None:
    author, rewrite = value["artifacts"]
    if (
        author["positions"] + rewrite["positions"]
        != value["execution"]["combined_positions"]
    ):
        raise ValueError("Aggregate position arithmetic drifted")
    if (
        sum(item["binary_calls"]["accepted"] for item in value["artifacts"])
        != value["execution"]["combined_binary_calls"]
    ):
        raise ValueError("Aggregate binary-call arithmetic drifted")
    if any(
        item["binary_calls"][key] != item["binary_calls"]["planned"]
        for item in value["artifacts"]
        for key in ("accepted", "settled")
    ):
        raise ValueError("Aggregate binary-call settlement drifted")
    difference = round(rewrite["score"] - author["score"], 4)
    if difference != value["comparison"]["score_difference_rewrite_minus_author"]:
        raise ValueError("Aggregate score difference drifted")
    if author["score_bounds"]["upper"] >= rewrite["score_bounds"]["lower"]:
        raise ValueError("Aggregate bounds relation drifted")


def _assert_surface(root: Path) -> None:
    files = {path.name for path in root.iterdir() if path.is_file()}
    directories = {path.name for path in root.iterdir() if path.is_dir()}
    if files != ALLOWED_FILES or directories:
        raise ValueError("Aggregate package surface drifted")
    if sha256((root / "README.md").read_bytes()).hexdigest() != README_SHA256:
        raise ValueError("Aggregate README binding drifted")
    public_text = "\n".join(
        (root / name).read_text(encoding="utf-8")
        for name in {"README.md", AGGREGATE_NAME}
    )
    if any(marker in public_text for marker in FORBIDDEN_TEXT_MARKERS):
        raise ValueError("Aggregate package text exposes a restricted detail")


def verify(root: Path = ROOT) -> dict[str, Any]:
    value = _read(root)
    if value != EXPECTED:
        raise ValueError("Aggregate identity drifted")
    _walk(value)
    if any(
        not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item)
        for item in value["opaque_execution_commitments"].values()
    ):
        raise ValueError("Opaque commitment is malformed")
    _assert_arithmetic(value)
    _assert_surface(root)
    return value


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
