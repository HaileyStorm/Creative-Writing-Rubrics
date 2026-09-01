from __future__ import annotations

import base64
import builtins
import importlib.util
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-candidates-v1"


def module():
    spec = importlib.util.spec_from_file_location("desc16", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def source_payloads(value):
    prior = value.predecessor()
    instruction, profile, _identity = prior.parent()
    return {
        item: prior.canonical(
            {
                "format_version": 1,
                "instruction": instruction.decode(),
                "profile": profile,
                "prompt": f"prompt:{group}",
                "response_schema": prior.RESPONSE_SCHEMA,
                "study_id": prior.SOURCE_STUDY_ID,
                "task": prior.SOURCE_TASK,
                "writing": f"writing:{item}",
            }
        )
        for item, group in prior.DEVELOPMENT_ITEMS
    }


def decoded(row):
    return json.loads(base64.b64decode(row["payload_base64"], validate=True))


def test_freezes_exact_parent_and_three_micro_descendants_across_52_cells():
    value = module()
    schedule = value.materialize(source_payloads(value))
    assert schedule["geometry"] == {
        "candidates": 4,
        "development_groups": 7,
        "development_items": 13,
        "grok_cells": 52,
        "sol_cells": 0,
    }
    assert len(schedule["cells"]) == 52
    assert schedule["candidates"][0]["candidate_id"] == value.PARENT_ID
    assert schedule["candidates"][0]["candidate_sha256"] == value.PARENT_CANDIDATE_SHA256
    assert {row["partition"] for row in schedule["cells"]} == {"development"}
    assert {row["route_name"] for row in schedule["cells"]} == {"grok_primary"}


def test_each_child_changes_only_the_referent_evidence_factor_at_a_lower_step():
    value = module()
    candidates = value.materialize(source_payloads(value))["candidates"]
    parent_profile = json.loads(base64.b64decode(candidates[0]["profile_base64"], validate=True))
    for child, (candidate_id, addendum) in zip(candidates[1:], value.CHILDREN, strict=True):
        child_profile = json.loads(base64.b64decode(child["profile_base64"], validate=True))
        assert child["candidate_id"] == candidate_id
        assert child["factor"] == value.FACTOR
        assert child_profile["factors"][value.FACTOR] == parent_profile["factors"][value.FACTOR] + "\n" + addendum
        assert [
            key
            for key in parent_profile["factors"]
            if child_profile["factors"][key] != parent_profile["factors"][key]
        ] == [value.FACTOR]
        assert len(addendum.split()) <= 22


def test_parent_payload_bytes_and_all_nonprofile_payload_fields_are_unchanged():
    value = module()
    source = source_payloads(value)
    prior_schedule = value.predecessor().materialize(source)
    schedule = value.materialize(source)
    old_parent = {
        row["item_id"]: base64.b64decode(row["payload_base64"], validate=True)
        for row in prior_schedule["cells"]
        if row["candidate_id"] == value.PARENT_ID
    }
    for item_id, old_parent_payload in old_parent.items():
        rows = [row for row in schedule["cells"] if row["item_id"] == item_id]
        parent = next(row for row in rows if row["candidate_id"] == value.PARENT_ID)
        assert base64.b64decode(parent["payload_base64"], validate=True) == old_parent_payload
        parent_value = decoded(parent)
        for row in rows:
            candidate_value = decoded(row)
            assert {key: item for key, item in candidate_value.items() if key != "profile"} == {
                key: item for key, item in parent_value.items() if key != "profile"
            }


def test_schedule_contains_no_targets_private_partitions_or_confirmation_data():
    value = module()
    schedule = value.materialize(source_payloads(value))
    assert schedule["authority"]["confirmation"] == "unopened"
    assert schedule["authority"]["reserve"] == "unopened"
    assert schedule["authority"]["sol"] == "veto_only_after_grok_qualification"
    forbidden = {"confirmation", "human_scores", "reserve", "reserve_target", "target", "target_score", "targets"}
    for cell in schedule["cells"]:
        payload = decoded(cell)
        stack = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                assert forbidden.isdisjoint(key.lower() for key in current)
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)


@pytest.mark.parametrize("field", ("confirmation", "human_scores", "reserve_target", "target"))
def test_source_payload_rejects_private_or_target_fields(field: str):
    value = module()
    source = source_payloads(value)
    item = next(iter(source))
    row = json.loads(source[item])
    row[field] = {"Coherence": 5} if field == "human_scores" else "private"
    source[item] = value.canonical(row)
    with pytest.raises(ValueError, match="field set|leakage"):
        value.materialize(source)


def test_deterministic_reconstruction_and_frozen_root_validation(tmp_path: Path):
    value = module()
    source = source_payloads(value)
    assert value.materialize(source) == value.materialize(source)
    root = tmp_path / "freeze"
    schedule = value.freeze(root, source)
    assert value.validate_frozen_root(root, source) == schedule
    (root / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        value.validate_frozen_root(root, source)


def test_predecessor_or_input_drift_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    source = source_payloads(value)
    altered = deepcopy(source)
    item = next(iter(altered))
    altered[item] = altered[item].replace(b'"writing"', b'"writinh"', 1)
    with pytest.raises(ValueError, match="payload|input|inventory|source"):
        value.materialize(altered)
    monkeypatch.setattr(value, "PREDECESSOR_STUDY_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="predecessor bytes"):
        value.materialize(source)


def test_contract_binds_cross_model_parent_evidence_without_promoting_it():
    value = module()
    contract = value.contract()
    evidence = contract["development_evidence"]
    assert evidence["grok"]["result_file_sha256"] == "624e59737f31759f7c3b4f880a813e77b35fe48576d60c199655a5ceb180f74d"
    assert evidence["sol"]["collector_file_sha256"] == "ff8905c0f4f537d5806e89294ab6432f56ef0c14bc083968f3405e6c6e580760"
    assert evidence["grok"]["commit"] == "87a27f63fec72e5c41721da15db41a9264290f38"
    assert evidence["sol"]["executor_commit"] == "cf9c58665eb33bb3b83264d1e9272c7e030cb18b"
    for commit in (evidence["grok"]["commit"], evidence["sol"]["executor_commit"]):
        assert subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=ROOT,
            check=False,
        ).returncode == 0
    assert evidence["sol"]["status"] == "local_collector_pending_public_verification"
    assert contract["authority"]["selection"] == "none"
    assert contract["lineage"]["parent_candidate_sha256"] == value.PARENT_CANDIDATE_SHA256


def test_runtime_import_has_no_dspy_or_optuna_dependency(monkeypatch: pytest.MonkeyPatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}:
            raise AssertionError(f"runtime optimizer import attempted: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    value = module()
    value.materialize(source_payloads(value))
    text = (PACKAGE / "study.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in text and "import optuna" not in text
