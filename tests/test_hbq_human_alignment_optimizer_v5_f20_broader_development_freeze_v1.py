"""Provider-free regressions for the broader next-wave freeze."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
NORMALIZED = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-normalized-d5e95ba-20260831a")
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")


def module():
    spec = importlib.util.spec_from_file_location("broader_freeze", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def build():
    return module().build(normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def test_real_inputs_freeze_exactly_five_candidates_seven_groups_and_35_bound_grok_cells():
    value = build()
    assert value["geometry"] == {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0}
    assert len(value["candidates"]) == len({row["candidate_id"] for row in value["candidates"]}) == 5
    assert len(value["groups"]) == len({row["prompt_group_id"] for row in value["groups"]}) == 7
    assert len(value["cells"]) == len({row["cell_id"] for row in value["cells"]}) == 35
    assert {row["partition"] for row in value["groups"]} == {"development"}
    assert {row["route_name"] for row in value["cells"]} == {"grok_primary"}
    assert value["authority"] == {"provider_calls_made": 0, "process_launches": 0, "selection": "none", "runtime": "none", "sol": "out_of_scope", "confirmation": {"status": "unopened", "cells": 0}}
    for row in value["cells"]:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert module().sha256(payload) == row["payload_sha256"]
        payload_json = json.loads(payload)
        assert payload_json["study_id"] == module().STUDY_ID
        assert payload_json["study_id"] != "hbq-human-alignment-optimizer-v1"
        assert module().sha256(module().canonical(payload_json["response_schema"])) == row["response_schema_sha256"]


def test_each_child_preserves_parent_instruction_and_changes_only_its_single_factor_addendum():
    value = build()
    candidates = module().descendants(NORMALIZED)
    parent = json.loads(candidates[0]["profile_bytes"])
    assert candidates[0]["candidate_sha256"] == module().PARENT_ARTIFACT_SHA256
    expected = {factor: addendum for _ordinal, factor, addendum in module().CHILDREN}
    for child in candidates[1:]:
        profile = json.loads(child["profile_bytes"])
        assert child["instruction_bytes"] == candidates[0]["instruction_bytes"]
        changed = [key for key in parent["factors"] if parent["factors"][key] != profile["factors"][key]]
        assert changed == [child["factor"]]
        assert profile["factors"][child["factor"]] == parent["factors"][child["factor"]] + "\n" + expected[child["factor"]]
        assert profile["factors"][child["factor"]].count(expected[child["factor"]]) == 1
        assert child["requested_step_fraction"] == 0.05
        assert child["step_semantics"] == "planning_prior_not_numeric_or_semantic_distance"
    assert value["parent_artifact_sha256"] == module().PARENT_ARTIFACT_SHA256


def test_parent_hash_and_leakage_are_rejected(tmp_path: Path):
    copied = tmp_path / "normalized"
    copied.mkdir()
    source = NORMALIZED / module().PARENT_FILE
    target = copied / module().PARENT_FILE
    shutil.copyfile(source, target)
    target.write_bytes(target.read_bytes().replace(b"conservative-hybrid", b"conservative-hybridx", 1))
    with pytest.raises(ValueError, match="parent artifact"):
        module().descendants(copied)
    assert all(row["partition"] == "development" for row in build()["groups"])


def test_public_groups_surface_returns_only_data_and_frozen_commitments_reject_addendum_tampering():
    study = module()
    frozen_groups = study.groups(frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    assert isinstance(frozen_groups, list)
    assert len(frozen_groups) == 7
    assert not any(hasattr(value, "freeze_grok_selection") or hasattr(value, "validate_sol_generalization") for value in frozen_groups)
    original = study.CHILDREN
    study.CHILDREN = ((original[0][0], original[0][1], original[0][2] + " tampered"), *original[1:])
    with pytest.raises(ValueError, match="frozen descendant or schedule commitment"):
        study.build(normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def test_freeze_writes_canonical_child_manifests_and_no_runtime_optimizer_or_provider_surface(tmp_path: Path):
    study = module()
    root = tmp_path / "freeze"
    value = study.freeze(output_root=root, normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    names = {path.name for path in root.iterdir()}
    assert names == {"schedule.json", *(f"{row['candidate_id']}.json" for row in value["candidates"])}
    assert (root / "schedule.json").read_bytes() == study.canonical(value)
    for row in value["candidates"]:
        manifest = json.loads((root / f"{row['candidate_id']}.json").read_bytes())
        assert study.canonical(manifest) == (root / f"{row['candidate_id']}.json").read_bytes()
        if row["kind"] != "admitted_parent":
            expected = dict(row)
            assert study.sha256({key: item for key, item in expected.items() if key != "manifest_sha256"}) == row["manifest_sha256"]
    source = (PACKAGE / "study.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert "allow_remote" not in source and "def execute" not in source


def test_persisted_schedule_payload_tamper_is_rejected(tmp_path: Path):
    study, root = module(), tmp_path / "freeze"
    study.freeze(output_root=root, normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    schedule_path = root / "schedule.json"
    schedule = json.loads(schedule_path.read_bytes())
    schedule["cells"][0]["payload_base64"] = schedule["cells"][1]["payload_base64"]
    schedule_path.write_bytes(study.canonical(schedule))
    with pytest.raises(ValueError, match="schedule commitment"):
        study.validate_frozen_root(root)


def test_persisted_candidate_tamper_and_inventory_drift_are_rejected(tmp_path: Path):
    study, root = module(), tmp_path / "freeze"
    schedule = study.freeze(output_root=root, normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    child = next(row for row in schedule["candidates"] if row["kind"] != "admitted_parent")
    child_path = root / f"{child['candidate_id']}.json"
    tampered = json.loads(child_path.read_bytes())
    tampered["addendum"] += " tampered"
    child_path.write_bytes(study.canonical(tampered))
    with pytest.raises(ValueError, match="persisted candidate manifest"):
        study.validate_frozen_root(root)
    child_path.write_bytes(study.canonical(child))
    (root / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        study.validate_frozen_root(root)
    (root / "extra.json").unlink()
    child_path.unlink()
    with pytest.raises(ValueError, match="inventory"):
        study.validate_frozen_root(root)


def test_persisted_reparse_is_rejected_when_supported(tmp_path: Path):
    study, root = module(), tmp_path / "freeze"
    study.freeze(output_root=root, normalized_root=NORMALIZED, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    link = root / "reparse.json"
    try:
        os.symlink(root / "schedule.json", link)
    except OSError:
        pytest.skip("symlink privilege is unavailable")
    with pytest.raises(ValueError, match="unsafe reparse|inventory"):
        study.validate_frozen_root(root)
