"""Provider-free selected-schedule contracts for the 100-story Dryad amendment."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_selected_schedule.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load():
    spec = importlib.util.spec_from_file_location("dryad_selected_schedule_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plan_root(tmp_path: Path):
    subject = load()
    root = tmp_path / "plan"
    root.mkdir()
    passes, requests = [], []
    for index in range(1, 237):
        partition = "TRAIN" if index <= 176 else "DEV"
        pass_id = f"baseline8-v1/{partition.lower()}/{index:04d}/story-{index:03d}"
        passes.append({"pass_id": pass_id, "partition": partition, "logical_sample_id": f"sample-{index:03d}"})
        for batch in range(1, 24):
            size = 2 if batch == 23 else 8
            requests.append({"ordinal": (index - 1) * 23 + batch, "pass_id": pass_id, "batch_number": batch,
                             "question_ids": [f"q{offset:03d}" for offset in range((batch - 1) * 8, (batch - 1) * 8 + size)]})
    plan = {"dispatch_batch_size": 8, "empirical_batch_cap": None, "passes": passes, "requests": requests}
    raw = canonical(plan)
    (root / "plan.json").write_bytes(raw)
    return subject, root, plan, digest(raw)


def test_first_partition_order_derives_exact_100_story_geometry(tmp_path: Path) -> None:
    subject, root, plan, plan_sha = plan_root(tmp_path)
    descriptor = subject.build_selected_schedule(
        plan_root=root, expected_plan_sha256=plan_sha,
        selected_train_ids=[row["pass_id"] for row in plan["passes"][:70]],
        selected_dev_ids=[row["pass_id"] for row in plan["passes"][176:206]],
    )
    assert descriptor["counts"] == {
        "stories": 100, "TRAIN": 70, "DEV": 30, "requests": 2300, "leaves_per_story": 178,
        "requests_per_story": 23, "grok_minimum_retained_prefix_requests": 80, "grok_remaining_requests": 2220,
    }
    assert descriptor["selected_request_ordinals"][:81] == list(range(1, 82))
    remaining = descriptor["grok_remaining_request_ordinals"]
    assert remaining[0] == 81 and remaining[remaining.index(1610) + 1] == 4049 and len(remaining) == 2220
    assert subject.verify_selected_schedule(descriptor=descriptor, plan_root=root, expected_plan_sha256=plan_sha) == descriptor


@pytest.mark.parametrize("kind", ["selection", "order", "hash"])
def test_schedule_rejects_selection_order_and_plan_hash_drift(tmp_path: Path, kind: str) -> None:
    subject, root, plan, plan_sha = plan_root(tmp_path)
    train = [row["pass_id"] for row in plan["passes"][:70]]
    dev = [row["pass_id"] for row in plan["passes"][176:206]]
    if kind == "selection":
        train[-1] = plan["passes"][70]["pass_id"]
        with pytest.raises(ValueError, match="first original"):
            subject.build_selected_schedule(plan_root=root, expected_plan_sha256=plan_sha, selected_train_ids=train, selected_dev_ids=dev)
        return
    descriptor = subject.build_selected_schedule(plan_root=root, expected_plan_sha256=plan_sha, selected_train_ids=train, selected_dev_ids=dev)
    if kind == "order":
        descriptor["selected_request_ordinals"][80], descriptor["selected_request_ordinals"][81] = descriptor["selected_request_ordinals"][81], descriptor["selected_request_ordinals"][80]
    else:
        descriptor["original_plan_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        subject.verify_selected_schedule(descriptor=descriptor, plan_root=root, expected_plan_sha256=plan_sha)


@pytest.mark.parametrize("fault", ["duplicate", "missing"])
def test_schedule_rejects_noncanonical_question_inventory(tmp_path: Path, fault: str) -> None:
    subject, root, plan, _plan_sha = plan_root(tmp_path)
    if fault == "duplicate":
        plan["requests"][1]["question_ids"][0] = plan["requests"][0]["question_ids"][0]
    else:
        plan["requests"][0]["question_ids"] = plan["requests"][0]["question_ids"][:-1]
    raw = canonical(plan)
    (root / "plan.json").write_bytes(raw)
    with pytest.raises(ValueError, match="Question|inventory"):
        subject.build_selected_schedule(
            plan_root=root, expected_plan_sha256=digest(raw),
            selected_train_ids=[row["pass_id"] for row in plan["passes"][:70]],
            selected_dev_ids=[row["pass_id"] for row in plan["passes"][176:206]],
        )
