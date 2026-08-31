import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evaluation-results" / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"


def load():
    spec = importlib.util.spec_from_file_location("fresh96_freeze", PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_open_schedule_is_64_cells_and_endpoint_neutral(tmp_path):
    module = load()
    schedule = module.build()
    assert schedule["geometry"] == {"groups": 16, "items": 32, "candidates": 2, "endpoint_neutral_logical_cells": 64}
    assert schedule["source"] == {"fresh96_manifest_sha256": module.MANIFEST_SHA256, "public_open_validation_only": True, "private_freeze_read": False}
    assert len(schedule["cells"]) == 64
    assert {row["candidate_id"] for row in schedule["cells"]} == {module.BASELINE, module.DESCENDANT}
    assert all("endpoint" not in row for row in schedule["cells"])
    root = tmp_path / "frozen"
    module.freeze(root)
    assert module.validate_frozen_root(root)["schedule_sha256"] == schedule["schedule_sha256"]


def test_admission_rejects_extra_artifact_and_tampered_payload(tmp_path):
    module = load()
    root = tmp_path / "frozen"
    module.freeze(root)
    (root / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        module.validate_frozen_root(root)
    (root / "extra.txt").unlink()
    raw = (root / "schedule.json").read_text(encoding="utf-8")
    (root / "schedule.json").write_text(raw.replace("payload_base64", "payloadXbase64", 1), encoding="utf-8")
    with pytest.raises(ValueError):
        module.validate_frozen_root(root)
