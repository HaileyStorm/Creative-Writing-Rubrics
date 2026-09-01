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
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v8-desc17-generalization-candidates-v1"


def module():
    spec = importlib.util.spec_from_file_location("desc17", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def source_payloads(value):
    prior = value.predecessor().predecessor()
    instruction, profile, _identity = prior.parent()
    return {
        item: prior.canonical({"format_version": 1, "instruction": instruction.decode(), "profile": profile, "prompt": f"prompt:{group}", "response_schema": prior.RESPONSE_SCHEMA, "study_id": prior.SOURCE_STUDY_ID, "task": prior.SOURCE_TASK, "writing": f"writing:{item}"})
        for item, group in prior.DEVELOPMENT_ITEMS
    }


def decode(row):
    return json.loads(base64.b64decode(row["payload_base64"], validate=True))


def test_freezes_parent_and_three_orthogonal_lower_step_descendants_over_exact_geometry():
    value = module()
    schedule = value.materialize(source_payloads(value))
    assert schedule["geometry"] == {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}
    assert len(schedule["cells"]) == 52
    assert schedule["candidates"][0]["candidate_id"] == value.PARENT_ID
    assert schedule["candidates"][0]["candidate_sha256"] == value.PARENT_CANDIDATE_SHA256
    assert [child["factor"] for child in schedule["candidates"][1:]] == ["human_reference_variant", "construct_framing", "human_reference_variant"]
    assert len({child["candidate_id"] for child in schedule["candidates"][1:]}) == 3
    assert len({child["addendum"] for child in schedule["candidates"][1:]}) == 3
    assert {row["partition"] for row in schedule["cells"]} == {"development"}
    assert {row["route_name"] for row in schedule["cells"]} == {"grok_primary"}


def test_contract_binds_the_pushed_desc16_sol_retention_result():
    value = module()
    assert value.contract()["accepted_parent_result"] == value.PARENT_SOL_VETO_RESULT
    assert value.PARENT_SOL_VETO_RESULT == {
        "commit": "cdefecdc9925559d240c4d0816395e7a7c7ad88c",
        "internal_result_sha256": "9a75197577ca14a012288ac699d730a20873a17872620e11e86a90975151244c",
        "result_file_sha256": "1860b579c7983d9de4296a2f845006b6432a0b7efa682b9090c985028ba838ff",
        "study_id": "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-result-v1",
    }
    result_path = "evaluation-results/hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-result-v1/result.json"
    completed = subprocess.run(
        ["git", "show", f"{value.PARENT_SOL_VETO_RESULT['commit']}:{result_path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    assert value.digest(completed.stdout) == value.PARENT_SOL_VETO_RESULT["result_file_sha256"]


def test_each_child_changes_exactly_one_declared_factor_and_retains_the_exact_clause():
    value = module()
    candidates = value.materialize(source_payloads(value))["candidates"]
    parent_profile = json.loads(base64.b64decode(candidates[0]["profile_base64"], validate=True))
    for child, (candidate_id, factor, addendum) in zip(candidates[1:], value.CHILDREN, strict=True):
        child_profile = json.loads(base64.b64decode(child["profile_base64"], validate=True))
        assert child["candidate_id"] == candidate_id
        assert child["factor"] == factor
        assert child_profile["factors"][factor] == parent_profile["factors"][factor] + "\n" + addendum
        assert [key for key in parent_profile["factors"] if child_profile["factors"][key] != parent_profile["factors"][key]] == [factor]


def test_parent_payload_is_byte_identical_and_each_candidate_is_endpoint_byte_bound():
    value = module()
    source = source_payloads(value)
    source_schedule = value.predecessor().materialize(source)
    schedule = value.materialize(source)
    source_parent = {row["item_id"]: base64.b64decode(row["payload_base64"], validate=True) for row in source_schedule["cells"] if row["candidate_id"] == value.PARENT_ID}
    for row in schedule["cells"]:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert row["endpoint_payload_sha256s"] == {"grok_primary": row["payload_sha256"], "sol_veto_if_qualified": row["payload_sha256"]}
        if row["candidate_id"] == value.PARENT_ID:
            assert payload == source_parent[row["item_id"]]
        else:
            parent = next(item for item in schedule["cells"] if item["candidate_id"] == value.PARENT_ID and item["item_id"] == row["item_id"])
            parent_value, child_value = decode(parent), decode(row)
            assert {key: item for key, item in child_value.items() if key != "profile"} == {key: item for key, item in parent_value.items() if key != "profile"}


def test_schedule_contains_no_targets_private_partitions_or_confirmation_data():
    value = module()
    schedule = value.materialize(source_payloads(value))
    assert schedule["authority"] == {"confirmation": "unopened", "dspy_optuna_runtime": "forbidden", "process_launches": 0, "provider_calls_made": 0, "reserve": "unopened", "selection": "none", "sol": "veto_only_after_grok_qualification"}
    forbidden = {"confirmation", "human_scores", "reference_score", "reserve", "reserve_target", "target", "target_score", "targets"}
    for cell in schedule["cells"]:
        stack = [decode(cell)]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                assert forbidden.isdisjoint(key.lower() for key in current)
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)


@pytest.mark.parametrize("field", ("confirmation", "human_scores", "reference_score", "reserve_target", "target"))
def test_source_payload_rejects_private_or_target_fields(field):
    value = module()
    source = source_payloads(value)
    item = next(iter(source))
    row = json.loads(source[item])
    row[field] = {"Coherence": 5} if field == "human_scores" else "private"
    source[item] = value.canonical(row)
    with pytest.raises(ValueError, match="field set|leakage"):
        value.materialize(source)


def test_deterministic_reconstruction_frozen_root_replay_and_mutation_rejection(tmp_path):
    value = module()
    source = source_payloads(value)
    assert value.materialize(source) == value.materialize(source)
    root = tmp_path / "freeze"
    schedule = value.freeze(root, source)
    assert value.validate_frozen_root(root, source) == schedule
    schedule_path = root / "schedule.json"
    schedule_path.write_bytes(schedule_path.read_bytes().replace(b'"grok_primary"', b'"grok_primarx"', 1))
    with pytest.raises(ValueError, match="persisted schedule|commitment|pairing|payload"):
        value.validate_frozen_root(root, source)


def test_predecessor_and_input_drift_are_rejected(monkeypatch):
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


def test_runtime_import_has_no_dspy_or_optuna_dependency(monkeypatch):
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
