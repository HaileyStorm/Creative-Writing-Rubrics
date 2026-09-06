from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
SOURCE = PACKAGE / "baseline_measurement_ledger.py"
PUBLIC_INPUTS = Path.home() / "Documents/cwr-dryad-pilot-source-freeze-20260905-r1/public-inputs.json"
PREPARED = Path.home() / "Documents/cwr-dryad-baseline8-plan-20260906-r1/plan.json"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"


def load():
    spec = importlib.util.spec_from_file_location("dryad_baseline_measurement_ledger", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepared_baseline_plan_binds_fixed_operational_geometry() -> None:
    subject = load()
    raw = PREPARED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PLAN_SHA256
    plan = json.loads(raw)
    core, _ = subject._core()
    geometry = subject._geometry(PUBLIC_INPUTS.read_bytes(), raw, PLAN_SHA256, core)
    groups = subject.cohort_groups(plan)
    assert plan["dispatch_batch_size"] == 8 and plan["empirical_batch_cap"] is None
    assert plan["execution_authority"] is False and plan["native_admission"] is False
    assert len(geometry.passes) == 236 and len(geometry.requests) == 5428
    assert len(groups) == 543 and [len(group) for group in groups] == [10] * 542 + [8]
    assert tuple(ordinal for group in groups for ordinal in group) == tuple(range(1, 5429))


def test_wrapper_rejects_malformed_or_short_baseline_geometry() -> None:
    subject = load()
    with pytest.raises(ValueError, match="geometry"):
        subject.cohort_groups({"requests": []})


def test_wrapper_rejects_reparse_sources_before_hash_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subject = load()
    original_lstat = Path.lstat

    def reparse(path: Path):
        info = original_lstat(path)
        if path == subject.PLAN_SOURCE:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ValueError, match="link or reparse"):
        subject._source(subject.PLAN_SOURCE, subject.PLAN_SOURCE_SHA256, "Baseline planner")

    link = tmp_path / "planner-link.py"
    try:
        link.symlink_to(subject.PLAN_SOURCE)
    except OSError:
        return
    monkeypatch.setattr(Path, "lstat", original_lstat)
    with pytest.raises(ValueError, match="link or reparse"):
        subject._source(link, subject.PLAN_SOURCE_SHA256, "Baseline planner")
