from __future__ import annotations

import base64
import importlib.util
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc15-referent-candidates-v1"


def module():
    spec = importlib.util.spec_from_file_location("desc15", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def payloads(value):
    instruction, profile, _identity = value.parent()
    return {item: value.canonical({"format_version": 1, "instruction": instruction.decode(), "profile": profile, "prompt": f"prompt:{group}", "response_schema": value.RESPONSE_SCHEMA, "study_id": value.SOURCE_STUDY_ID, "task": value.SOURCE_TASK, "writing": f"writing:{item}"}) for item, group in value.DEVELOPMENT_ITEMS}


def test_freezes_exact_children_and_52_cell_development_only_schedule():
    value = module(); schedule = value.materialize(payloads(value))
    assert len(schedule["candidates"]) == 4 and len(schedule["cells"]) == 52
    assert schedule["geometry"] == {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0}
    parent = schedule["candidates"][0]
    for child, (_identifier, factor, addendum) in zip(schedule["candidates"][1:], value.CHILDREN, strict=True):
        base, altered = json.loads(base64.b64decode(parent["profile_base64"])), json.loads(base64.b64decode(child["profile_base64"]))
        assert child["factor"] == factor and altered["factors"][factor] == base["factors"][factor] + "\n" + addendum
        assert [key for key in base["factors"] if altered["factors"][key] != base["factors"][key]] == [factor]
    assert {row["partition"] for row in schedule["cells"]} == {"development"}
    assert all(row["route_name"] == "grok_primary" for row in schedule["cells"])


def test_freeze_reparse_and_drift_guards(tmp_path: Path):
    value = module(); source = payloads(value); root = tmp_path / "freeze"; schedule = value.freeze(root, source)
    assert value.validate_frozen_root(root, source) == schedule
    altered = deepcopy(source); altered[next(iter(altered))] = altered[next(iter(altered))].replace(b'"profile"', b'"profily"', 1)
    with pytest.raises(ValueError, match="payload|input"):
        value.validate_frozen_root(root, altered)
    (root / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        value.validate_frozen_root(root, source)


def test_no_wrong_items_or_private_partition_markers_can_enter_schedule():
    value = module(); source = payloads(value)
    source["item-wrong"] = source.pop(next(iter(source)))
    with pytest.raises(ValueError, match="inventory"):
        value.materialize(source)
    source = payloads(value); bad = next(iter(source)); source[bad] = source[bad][:-2] + b',"note":"Fresh96"}\n'
    with pytest.raises(ValueError, match="noncanonical|leakage"):
        value.materialize(source)
    assert "import dspy" not in (PACKAGE / "study.py").read_text().lower()
    assert "import optuna" not in (PACKAGE / "study.py").read_text().lower()


@pytest.mark.parametrize("field", ("target", "partition", "reserve_target", "human_scores"))
def test_payload_allowlist_rejects_targets_and_private_partition_fields(field: str):
    value = module(); source = payloads(value); item = next(iter(source)); row = json.loads(source[item])
    row[field] = {"Coherence": 5} if field == "human_scores" else "confirmation"
    source[item] = value.canonical(row)
    with pytest.raises(ValueError, match="exact provider-ready|leakage"):
        value.materialize(source)


@pytest.mark.parametrize("mutation", ("missing", "study_alias", "schema"))
def test_payload_requires_full_bound_provider_ready_shape(mutation: str):
    value = module(); source = payloads(value); item = next(iter(source)); row = json.loads(source[item])
    if mutation == "missing": row.pop("response_schema")
    elif mutation == "study_alias": row["study_id"] = "Fresh_96 confirmation"
    else: row["response_schema"]["format_version"] = 2
    source[item] = value.canonical(row)
    with pytest.raises(ValueError, match="exact provider-ready|source identity|response schema"):
        value.materialize(source)


def test_contract_is_exact_and_not_advisory(monkeypatch: pytest.MonkeyPatch):
    value = module(); assert value.contract()["lineage"]["public_evidence_commit"] == value.PUBLIC_EVIDENCE_COMMIT
    monkeypatch.setattr(value, "contract", lambda: (_ for _ in ()).throw(ValueError("study contract drifted")))
    with pytest.raises(ValueError, match="contract"):
        value.materialize(payloads(value))


def test_exclusive_writes_and_reparse_artifacts_are_rejected(tmp_path: Path):
    value = module(); target = tmp_path / "target.json"; target.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="fresh plain"):
        value._safe_write(target, b"{}\n")
    root = tmp_path / "freeze"; source = payloads(value); value.freeze(root, source)
    replacement = tmp_path / "replacement.json"; replacement.write_bytes((root / "schedule.json").read_bytes())
    (root / "schedule.json").unlink()
    try:
        os.symlink(replacement, root / "schedule.json")
    except OSError:
        pytest.skip("symlink privilege is unavailable")
    with pytest.raises(ValueError, match="reparse"):
        value.validate_frozen_root(root, source)


def test_freeze_rejects_plain_directory_swap_between_exclusive_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module(); source = payloads(value); root = tmp_path / "freeze"; moved = tmp_path / "moved"; original = value._safe_write; calls = 0
    def swap(path: Path, raw: bytes, **kwargs):
        nonlocal calls
        original(path, raw, **kwargs); calls += 1
        if calls == 1:
            root.replace(moved); root.mkdir(); (root / "schedule.json").write_bytes((moved / "schedule.json").read_bytes())
    monkeypatch.setattr(value, "_safe_write", swap)
    with pytest.raises(ValueError, match="freeze root changed"):
        value.freeze(root, source)
